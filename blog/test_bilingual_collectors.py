from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import BlogUser
from blog.models import Article, Category
from blog.services.collectors import normalize_rewritten_article, parse_rewritten_article, publish_rewritten_article


class BilingualCollectorParsingTest(TestCase):
    def setUp(self):
        self.category, _ = Category.objects.get_or_create(name='文章')
        self.author = BlogUser.objects.create_superuser(
            username='collector-admin',
            email='collector@example.com',
            password='password',
        )

    def test_parse_rewritten_article_accepts_json_object(self):
        rewritten = parse_rewritten_article(
            '{"title_zh":"中文标题","body_zh":"中文正文","title_en":"English Title","body_en":"English body","seo_description_en":"English summary"}'
        )

        self.assertEqual(rewritten['title_zh'], '中文标题')
        self.assertEqual(rewritten['body_zh'], '中文正文')
        self.assertEqual(rewritten['title_en'], 'English Title')
        self.assertEqual(rewritten['body_en'], 'English body')
        self.assertEqual(rewritten['seo_description_en'], 'English summary')

    def test_normalize_rewritten_article_accepts_legacy_markdown(self):
        rewritten = normalize_rewritten_article('# 中文标题\n\n中文正文')

        self.assertEqual(rewritten['title_zh'], '中文标题')
        self.assertEqual(rewritten['body_zh'], '中文正文')
        self.assertEqual(rewritten['title_en'], '')

    def test_publish_rewritten_article_stores_english_fields(self):
        article = publish_rewritten_article(
            {
                'title': 'Source title',
                'summary': 'Source summary',
                'url': 'https://example.com/source',
                'published_at': timezone.now(),
                'feed_category': '后端开发',
                'feed_tags': ('Python',),
            },
            {
                'title_zh': '中文标题',
                'body_zh': '中文正文',
                'title_en': 'English Title',
                'body_en': '# English Title\n\nEnglish body',
                'seo_description_en': 'English summary',
            },
        )

        self.assertEqual(article.title, '中文标题')
        self.assertIn('中文正文', article.body)
        self.assertEqual(article.title_en, 'English Title')
        self.assertEqual(article.body_en, 'English body')
        self.assertEqual(article.seo_description_en, 'English summary')


class BackfillArticleEnglishCommandTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Backfill')
        self.author = BlogUser.objects.create_user(
            username='backfill-author',
            email='backfill@example.com',
            password='password',
        )
        self.article = Article.objects.create(
            title='中文回填标题',
            body='中文回填正文',
            author=self.author,
            category=self.category,
            status='p',
            type='a',
        )

    def test_backfill_dry_run_reports_candidates_without_writing(self):
        out = StringIO()

        call_command('backfill_article_english', dry_run=True, limit=1, stdout=out)

        self.article.refresh_from_db()
        self.assertIn(str(self.article.pk), out.getvalue())
        self.assertEqual(self.article.title_en, '')
        self.assertEqual(self.article.body_en, '')

    @patch('blog.management.commands.backfill_article_english.rewrite_article')
    def test_backfill_writes_english_content(self, rewrite_article_mock):
        rewrite_article_mock.return_value = {
            'title_en': 'Backfilled English Title',
            'body_en': '# Backfilled English Title\n\nBackfilled English body',
            'seo_description_en': 'Backfilled SEO',
        }

        call_command('backfill_article_english', limit=1)

        self.article.refresh_from_db()
        self.assertEqual(self.article.title_en, 'Backfilled English Title')
        self.assertEqual(self.article.body_en, 'Backfilled English body')
        self.assertEqual(self.article.seo_description_en, 'Backfilled SEO')
