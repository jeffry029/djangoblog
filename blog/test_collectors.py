import os
from datetime import datetime, timedelta, timezone as datetime_timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from blog.services.collectors import (
    DEFAULT_TECH_FEEDS,
    FetchUrlError,
    determine_article_taxonomy,
    entry_published_at,
    fetch_url,
    is_before_cutoff,
    get_env_int,
    get_optional_env_int,
    normalize_feed_configs,
    parse_aihot_feed,
    parse_feed_entries,
    parse_feed_configs,
    parse_feed_list,
    rewrite_article,
    should_log_collector_tracebacks,
    sort_feed_entries,
)


class FetchUrlTest(SimpleTestCase):
    @patch.dict(os.environ, {'COLLECTOR_PROXY_URL': 'http://127.0.0.1:7890'}, clear=False)
    @patch('blog.services.collectors.request_url')
    def test_fetch_url_retries_with_proxy_after_direct_failure(self, request_url_mock):
        request_url_mock.side_effect = [
            requests.ReadTimeout('direct timeout'),
            '<feed />',
        ]

        result = fetch_url('https://go.dev/blog/feed.atom')

        self.assertEqual(result, '<feed />')
        self.assertIsNone(request_url_mock.call_args_list[0].kwargs.get('proxies'))
        self.assertEqual(
            request_url_mock.call_args_list[1].kwargs['proxies'],
            {
                'http': 'http://127.0.0.1:7890',
                'https': 'http://127.0.0.1:7890',
            },
        )

    @patch.dict(os.environ, {'COLLECTOR_PROXY_URL': ''}, clear=False)
    @patch('blog.services.collectors.request_url')
    def test_fetch_url_allows_proxy_fallback_to_be_disabled(self, request_url_mock):
        request_url_mock.side_effect = requests.ReadTimeout('direct timeout')

        with self.assertRaises(FetchUrlError) as context:
            fetch_url('https://go.dev/blog/feed.atom')

        self.assertIn('direct failed', str(context.exception))
        self.assertEqual(request_url_mock.call_count, 1)

    @override_settings(DEBUG=False, COLLECTOR_LOG_TRACEBACKS=False)
    def test_collector_tracebacks_are_disabled_by_default(self):
        self.assertFalse(should_log_collector_tracebacks())

    @override_settings(DEBUG=False, COLLECTOR_LOG_TRACEBACKS=True)
    def test_collector_tracebacks_can_be_enabled(self):
        self.assertTrue(should_log_collector_tracebacks())


class FeedCollectorParsingTest(SimpleTestCase):
    def test_parse_aihot_feed_extracts_content_and_source_links(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
          <channel>
            <item>
              <title><![CDATA[Agent runtime released]]></title>
              <link>https://aihot.virxact.com/items/agent-runtime</link>
              <description><![CDATA[Runtime details for agent builders.

阅读原文：https://example.com/agent-runtime

via AI HOT · https://aihot.virxact.com/items/agent-runtime]]></description>
              <content:encoded><![CDATA[
                <p>Full <strong>release</strong> details.</p>
                <p><a href="/docs">Read docs</a></p>
                <script>alert('bad')</script>
                <p>—— 本文由 AI HOT 聚合整理，完整版与更多 AI 动态见 AI HOT</p>
              ]]></content:encoded>
              <category>AI 产品</category>
              <pubDate>Fri, 17 Jul 2026 00:40:20 GMT</pubDate>
              <guid isPermaLink="false">agent-runtime</guid>
              <author>noreply@aihot.virxact.com (Example Engineering)</author>
            </item>
          </channel>
        </rss>
        """

        entries = parse_aihot_feed(xml)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['title'], 'Agent runtime released')
        self.assertEqual(entries[0]['summary'], 'Runtime details for agent builders.')
        self.assertEqual(entries[0]['source_name'], 'Example Engineering')
        self.assertEqual(entries[0]['source_url'], 'https://aihot.virxact.com/items/agent-runtime')
        self.assertEqual(entries[0]['original_url'], 'https://example.com/agent-runtime')
        self.assertEqual(entries[0]['tags'], 'AI 产品')
        self.assertIn('<strong>release</strong>', entries[0]['content'])
        self.assertIn('href="https://aihot.virxact.com/docs"', entries[0]['content'])
        self.assertNotIn('script', entries[0]['content'])
        self.assertNotIn('本文由 AI HOT', entries[0]['content'])
        self.assertEqual(entries[0]['published_at'].year, 2026)

    def test_parse_aihot_feed_handles_html_summary_and_full_feed_content(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
          <channel><item>
            <title><![CDATA[HTML feed item]]></title>
            <link>https://aihot.virxact.com/items/html-feed-item</link>
            <description><![CDATA[
              <p>Summary paragraph with <strong>formatting</strong>.</p>
              <p>🔗 <a href="https://example.com/original">阅读原文</a></p>
              <p>via AIHOT · <a href="https://aihot.virxact.com/items/html-feed-item">detail</a></p>
            ]]></description>
            <content:encoded><![CDATA[<p>Full article body.</p>]]></content:encoded>
            <pubDate>Fri, 17 Jul 2026 00:40:20 GMT</pubDate>
          </item></channel>
        </rss>"""

        entry = parse_aihot_feed(xml)[0]

        self.assertEqual(entry['summary'], 'Summary paragraph with formatting.')
        self.assertEqual(entry['original_url'], 'https://example.com/original')
        self.assertEqual(entry['content'], '<p>Full article body.</p>')

    def test_parse_aihot_items_ignores_tag_container_text(self):
        from blog.services.collectors import parse_aihot_items

        html = """
        <article class="news-card">
          <a href="/items/agent-google">Google updates agent products</a>
          <div class="tag-list">
            <span class="tag">智能体</span>
            <span class="tag">Google</span>
            <span class="tag">产品更新</span>
          </div>
        </article>
        """

        entries = parse_aihot_items(html, base_url='https://example.com/')

        self.assertEqual(entries[0]['tags'], '智能体,Google,产品更新')

    def test_parse_rss_entries_uses_channel_title_and_pubdate(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Example Engineering</title>
            <item>
              <title>Scaling Django Workers</title>
              <link>https://example.com/django-workers</link>
              <description><![CDATA[<p>Worker queue tuning notes.</p>]]></description>
              <pubDate>Wed, 13 May 2026 10:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>
        """

        entries = parse_feed_entries(xml, 'https://example.com/feed.xml')

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['title'], 'Scaling Django Workers')
        self.assertEqual(entries[0]['source_name'], 'Example Engineering')
        self.assertEqual(entries[0]['summary'], 'Worker queue tuning notes.')
        self.assertEqual(entries[0]['published_at'].year, 2026)

    def test_parse_atom_entries_uses_feed_title_and_updated_time(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>AI Framework Blog</title>
          <entry>
            <title>New Inference Runtime</title>
            <link href="https://example.com/runtime" rel="alternate" />
            <summary>Runtime changes for model serving.</summary>
            <updated>2026-05-12T08:30:00+00:00</updated>
          </entry>
        </feed>
        """

        entries = parse_feed_entries(xml, 'https://example.com/atom.xml')

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['title'], 'New Inference Runtime')
        self.assertEqual(entries[0]['source_name'], 'AI Framework Blog')
        self.assertEqual(entries[0]['url'], 'https://example.com/runtime')
        self.assertEqual(entries[0]['published_at'].day, 12)

    def test_sort_feed_entries_newest_first_with_missing_dates_last(self):
        older = datetime(2026, 5, 11, tzinfo=datetime_timezone.utc)
        newer = datetime(2026, 5, 13, tzinfo=datetime_timezone.utc)
        entries = [
            {'title': 'missing'},
            {'title': 'older', 'published_at': older},
            {'title': 'newer', 'published_at': newer},
        ]

        sorted_entries = sort_feed_entries(entries)

        self.assertEqual([entry['title'] for entry in sorted_entries], ['newer', 'older', 'missing'])

    def test_entry_published_at_normalizes_naive_datetimes_for_cutoff_compare(self):
        published_at = entry_published_at({
            'published_at': datetime(2026, 5, 13, 10, 30, 0),
        })
        cutoff = datetime(2026, 5, 13, 1, 0, 0, tzinfo=datetime_timezone.utc)

        self.assertIsNotNone(published_at)
        self.assertTrue(timezone.is_aware(published_at))
        self.assertTrue(published_at > cutoff)

    def test_is_before_cutoff_handles_aware_published_at_and_naive_cutoff(self):
        published_at = datetime(2026, 5, 13, 10, 30, 0, tzinfo=datetime_timezone.utc)
        cutoff = datetime(2026, 5, 13, 9, 0, 0)

        self.assertFalse(is_before_cutoff(published_at, cutoff))


class FeedCollectorConfigTest(SimpleTestCase):
    @patch.dict(os.environ, {'TECH_BLOG_FEEDS': ''}, clear=False)
    def test_parse_feed_list_uses_default_feeds(self):
        self.assertEqual(parse_feed_list(), DEFAULT_TECH_FEEDS)
        self.assertGreaterEqual(len(DEFAULT_TECH_FEEDS), 35)
        self.assertIn('https://go.dev/blog/feed.atom', DEFAULT_TECH_FEEDS)
        self.assertIn('https://nextjs.org/feed.xml', DEFAULT_TECH_FEEDS)
        self.assertIn('https://nodejs.org/en/feed/blog.xml', DEFAULT_TECH_FEEDS)

    def test_default_feeds_do_not_include_known_dead_or_duplicate_urls(self):
        stale_urls = {
            'https://blog.golang.org/feed.atom',
            'https://blog.vuejs.org/feed.xml',
            'https://www.docker.com/blog/feed/',
            'https://cloud.google.com/blog/rss',
            'https://planet.mysql.com/rss20.xml',
            'https://pytorch.org/blog/feed.xml',
            'https://tech.meituan.com/feed/',
        }

        self.assertFalse(stale_urls.intersection(DEFAULT_TECH_FEEDS))

    @patch.dict(os.environ, {'TECH_BLOG_FEEDS': ' https://a.test/feed.xml,https://b.test/rss '}, clear=False)
    def test_parse_feed_list_uses_env_feeds(self):
        self.assertEqual(parse_feed_list(), ['https://a.test/feed.xml', 'https://b.test/rss'])

    @patch.dict(
        os.environ,
        {
            'TECH_BLOG_FEEDS': '',
            'TECH_BLOG_EXTRA_FEEDS': ' https://example.com/react-weekly.xml,https://example.com/platform/go/feed.xml ',
        },
        clear=False,
    )
    def test_parse_feed_configs_appends_extra_feeds(self):
        configs = parse_feed_configs()
        urls = [config.url for config in configs]

        self.assertIn('https://example.com/react-weekly.xml', urls)
        self.assertIn('https://example.com/platform/go/feed.xml', urls)

    def test_normalize_feed_configs_uses_default_metadata(self):
        configs = normalize_feed_configs(['https://nextjs.org/feed.xml', 'https://go.dev/blog/feed.atom'])

        self.assertEqual(configs[0].category, '前端开发')
        self.assertIn('Next.js', configs[0].tags)
        self.assertEqual(configs[1].category, '后端开发')
        self.assertIn('Go', configs[1].tags)

    def test_determine_article_taxonomy_uses_keywords_for_general_feed(self):
        category_name, tag_names = determine_article_taxonomy({
            'title': 'Scaling PostgreSQL and Redis for high-throughput APIs',
            'summary': 'Practical notes on query tuning, cache invalidation, and service latency.',
            'source_name': 'InfoQ',
            'feed_category': '',
            'feed_tags': ('InfoQ', '全栈'),
        })

        self.assertEqual(category_name, '文章')
        self.assertIn('PostgreSQL', tag_names)
        self.assertIn('Redis', tag_names)
        self.assertIn('数据库', tag_names)

    @patch.dict(os.environ, {'TECH_ARTICLE_LIMIT': '12', 'BAD_INT': 'abc'}, clear=False)
    def test_env_int_helpers(self):
        self.assertEqual(get_env_int('TECH_ARTICLE_LIMIT', 5), 12)
        self.assertEqual(get_env_int('BAD_INT', 5), 5)
        self.assertIsNone(get_optional_env_int('MISSING_INT'))


class FeedCollectorPublishingTest(SimpleTestCase):
    @patch.dict(os.environ, {
        'OPENAI_API_KEY': 'test-key',
        'OPENAI_BASE_URL': 'https://llm.example/v1',
        'BLOG_LLM_MODEL': 'test-model',
    }, clear=True)
    @patch('openai.OpenAI')
    def test_rewrite_article_uses_compatible_default_user_agent(self, openai_mock):
        openai_mock.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"title_zh": "测试", "body_zh": "正文"}'))],
            usage=None,
        )

        result = rewrite_article({
            'title': 'HTTP client compatibility',
            'summary': 'Test the configured user agent.',
            'url': 'https://example.com/http-client-compatibility',
        })

        self.assertEqual(result['body_zh'], '正文')
        openai_mock.assert_called_once_with(
            api_key='test-key',
            base_url='https://llm.example/v1',
            default_headers={'User-Agent': 'curl/8.5.0'},
        )

    @patch('blog.services.collectors.Tag.objects.get_or_create')
    @patch('blog.services.collectors.Article.objects.create')
    @patch('blog.services.collectors.Category.objects.get_or_create')
    @patch('blog.services.collectors.get_default_author')
    def test_publish_rewritten_article_assigns_category_and_tags(
        self,
        get_default_author_mock,
        category_get_or_create_mock,
        article_create_mock,
        tag_get_or_create_mock,
    ):
        from blog.services.collectors import publish_rewritten_article

        fake_category = SimpleNamespace(name='文章', name_en='Articles')
        fake_author = SimpleNamespace(username='collector-admin')
        fake_article = Mock()
        fake_article.tags = Mock()

        get_default_author_mock.return_value = fake_author
        category_get_or_create_mock.return_value = (fake_category, True)
        article_create_mock.return_value = fake_article
        tag_get_or_create_mock.side_effect = lambda name: (SimpleNamespace(name=name), True)

        article = publish_rewritten_article(
            {
                'title': 'Go runtime tuning for API services',
                'summary': 'Latency tuning, goroutines, and service concurrency.',
                'url': 'https://example.com/go-runtime-tuning',
                'published_at': timezone.now(),
                'feed_category': '后端开发',
                'feed_tags': ('Go', '并发'),
            },
            '# Go runtime tuning for API services\n\nUse worker pools and profile allocations.',
        )

        self.assertIs(article, fake_article)
        category_get_or_create_mock.assert_called_once_with(name='文章')
        added_tag_names = [call.args[0].name for call in fake_article.tags.add.call_args_list]
        self.assertEqual(set(added_tag_names), {'Go', '并发', '后端'})

    @patch('blog.services.collectors.timezone.now')
    @patch('blog.services.collectors.Tag.objects.get_or_create')
    @patch('blog.services.collectors.Article.objects.create')
    @patch('blog.services.collectors.Category.objects.get_or_create')
    @patch('blog.services.collectors.get_default_author')
    def test_publish_rewritten_article_clamps_future_pub_time(
        self,
        get_default_author_mock,
        category_get_or_create_mock,
        article_create_mock,
        tag_get_or_create_mock,
        timezone_now_mock,
    ):
        from blog.services.collectors import publish_rewritten_article

        fixed_now = datetime(2026, 5, 14, 21, 30, 0)
        timezone_now_mock.return_value = fixed_now
        get_default_author_mock.return_value = SimpleNamespace(username='collector-admin')
        category_get_or_create_mock.return_value = (SimpleNamespace(name='文章', name_en='Articles'), True)
        article_create_mock.return_value = Mock(tags=Mock())
        tag_get_or_create_mock.side_effect = lambda name: (SimpleNamespace(name=name), True)

        publish_rewritten_article(
            {
                'title': 'Future-dated feed entry',
                'summary': 'A feed item that landed slightly ahead of local time.',
                'url': 'https://example.com/future-entry',
                'published_at': fixed_now + timedelta(hours=8),
                'feed_category': 'AI 工程',
                'feed_tags': ('OpenAI',),
            },
            '# Future-dated feed entry\n\nExample content.',
        )

        self.assertEqual(article_create_mock.call_args.kwargs['pub_time'], fixed_now)
