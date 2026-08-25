import re

from django.core.management.base import BaseCommand, CommandError

from blog.models import Article
from blog.services.collectors import (
    append_source_link,
    extract_markdown_title,
    extract_source_url,
    is_publishable_rewrite,
    normalize_rewritten_article,
    rewrite_article,
    strip_leading_markdown_title,
    strip_source_link_lines,
)


class Command(BaseCommand):
    help = '使用技术文章写作 skill 重写最新一篇采集文章'

    def add_arguments(self, parser):
        parser.add_argument('--article-id', type=int)

    def handle(self, *args, **options):
        article_id = options.get('article_id')
        if article_id:
            article = Article.objects.filter(pk=article_id).first()
        else:
            article = Article.objects.filter(
                type='a',
                status='p',
                category__name='文章',
            ).order_by('-id').first()

        if not article:
            raise CommandError('没有找到可重写的文章')

        source_url = extract_source_url(article.body)
        if not source_url:
            raise CommandError(f'文章 {article.pk} 没有可识别的原文链接')

        summary = build_summary(article.body)
        rewritten = rewrite_article({
            'title': article.title,
            'summary': summary,
            'url': source_url,
        })
        if not is_publishable_rewrite(rewritten):
            raise CommandError('LLM 未返回符合发布要求的内容')

        rewritten = normalize_rewritten_article(rewritten)
        title = rewritten.get('title_zh') or extract_markdown_title(rewritten.get('body_zh', '')) or article.title
        body = strip_source_link_lines(rewritten.get('body_zh') or '')
        body = strip_leading_markdown_title(body, title)
        article.title = title[:200]
        article.body = append_source_link(body, source_url)
        article.title_en = (rewritten.get('title_en') or '')[:200]
        article.body_en = strip_source_link_lines(rewritten.get('body_en') or '')
        if article.title_en:
            article.body_en = strip_leading_markdown_title(article.body_en, article.title_en)
        article.seo_description_en = rewritten.get('seo_description_en') or ''
        article.save(update_fields=[
            'title',
            'body',
            'title_en',
            'body_en',
            'seo_description_en',
            'last_modify_time',
        ])

        self.stdout.write(self.style.SUCCESS(
            f'Rewritten article {article.pk}: {article.title}'
        ))


def build_summary(body):
    body = re.sub(r'\[原文链接\]\([^)]+\)', '', body)
    body = re.sub(r'原文链接[:：]\s*https?://\S+', '', body)
    body = re.sub(r'```.*?```', '', body, flags=re.S)
    text = re.sub(r'[#>*_`\\[\\]()]', ' ', body)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:2400]
