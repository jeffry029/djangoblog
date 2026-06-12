from types import SimpleNamespace

from django.test import TestCase
from django.utils import translation

from accounts.models import BlogUser
from blog.models import Article, Category
from djangoblog.feeds import DjangoBlogFeed
from djangoblog.sitemap import ArticleSiteMap


class BilingualSeoDiscoveryTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='SEO Category')
        self.author = BlogUser.objects.create_user(
            username='seo-author',
            email='seo@example.com',
            password='password',
        )

    def create_article(self, **kwargs):
        defaults = {
            'title': '中文 SEO 标题',
            'body': '中文 SEO 正文',
            'author': self.author,
            'category': self.category,
            'status': 'p',
            'type': 'a',
        }
        defaults.update(kwargs)
        return Article.objects.create(**defaults)

    def test_sitemap_includes_english_only_when_article_has_english_content(self):
        translated = self.create_article(
            title='中文双语',
            body='中文正文',
            title_en='English Sitemap Title',
            body_en='English sitemap body',
        )
        untranslated = self.create_article(title='只有中文', body='只有中文正文')
        sitemap = ArticleSiteMap()

        self.assertEqual(sitemap.get_languages_for_item(translated), ['zh-hans', 'en'])
        self.assertEqual(sitemap.get_languages_for_item(untranslated), ['zh-hans'])

        urls = sitemap.get_urls(site=SimpleNamespace(domain='example.com'), protocol='https')
        locations = [item['location'] for item in urls]

        self.assertTrue(any(f'/en/article/' in location and location.endswith(f'/{translated.pk}.html') for location in locations))
        self.assertFalse(any(f'/en/article/' in location and location.endswith(f'/{untranslated.pk}.html') for location in locations))

    def test_feed_prefers_english_content_under_english_locale(self):
        article = self.create_article(
            title='中文 Feed 标题',
            body='中文 Feed 正文',
            title_en='English Feed Title',
            body_en='English feed body',
        )
        feed = DjangoBlogFeed()

        with translation.override('en'):
            self.assertEqual(feed.item_title(article), 'English Feed Title')
            self.assertIn('English feed body', feed.item_description(article))

    def test_feed_metadata_uses_active_language(self):
        feed = DjangoBlogFeed()

        with translation.override('en'):
            self.assertEqual(feed.title(), 'Developer Radar')
            self.assertIn('AI-curated technical articles', feed.description())

        with translation.override('zh-hans'):
            self.assertEqual(feed.title(), '开发者雷达')
            self.assertIn('AI 精选', feed.description())
