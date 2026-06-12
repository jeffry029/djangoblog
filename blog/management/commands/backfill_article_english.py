import re

from django.core.management.base import BaseCommand, CommandError

from blog.models import Article
from blog.services.collectors import (
    normalize_rewritten_article,
    rewrite_article,
    strip_leading_markdown_title,
    strip_source_link_lines,
)


class Command(BaseCommand):
    help = '为缺少英文内容的已发布文章批量生成英文标题、正文和 SEO 摘要'

    def add_arguments(self, parser):
        parser.add_argument('--article-id', type=int)
        parser.add_argument('--limit', type=int, default=5)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        queryset = Article.objects.filter(type='a', status='p').order_by('id')
        if options.get('article_id'):
            queryset = queryset.filter(pk=options['article_id'])
        else:
            queryset = queryset.filter(body_en='')

        limit = max(options.get('limit') or 1, 1)
        candidates = list(queryset[:limit])
        if not candidates:
            self.stdout.write('No articles need English backfill.')
            return

        if options.get('dry_run'):
            ids = ', '.join(str(article.pk) for article in candidates)
            self.stdout.write(f'Would backfill {len(candidates)} article(s): {ids}')
            return

        updated = 0
        for article in candidates:
            rewritten = rewrite_article({
                'title': article.title,
                'summary': build_summary(article.body),
                'url': article.get_full_url(),
            })
            normalized = normalize_rewritten_article(rewritten)
            if not normalized.get('body_en') or not normalized.get('title_en'):
                self.stderr.write(f'Skipped article {article.pk}: LLM returned no English content')
                continue

            article.title_en = normalized['title_en'][:200]
            article.body_en = strip_source_link_lines(normalized['body_en'])
            article.body_en = strip_leading_markdown_title(article.body_en, article.title_en)
            article.seo_description_en = normalized.get('seo_description_en', '')
            article.save(update_fields=['title_en', 'body_en', 'seo_description_en', 'last_modify_time'])
            updated += 1
            self.stdout.write(f'Backfilled article {article.pk}: {article.title_en}')

        if updated == 0:
            raise CommandError('No articles were backfilled')
        self.stdout.write(self.style.SUCCESS(f'Backfilled {updated} article(s).'))


def build_summary(body):
    body = re.sub(r'\[原文链接\]\([^)]+\)', '', body or '')
    body = re.sub(r'原文链接[:：]\s*https?://\S+', '', body)
    body = re.sub(r'```.*?```', '', body, flags=re.S)
    text = re.sub(r'[#>*_`\\[\\]()]', ' ', body)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:2400]
