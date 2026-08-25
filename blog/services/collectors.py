import os
import re
import time
import hashlib
import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone

from blog.models import Article, Category, NewsItem, Tag
from djangoblog.indexnow import notify_indexnow_articles
from djangoblog.utils import cache, sanitize_html


logger = logging.getLogger(__name__)
AIHOT_URL = 'https://aihot.virxact.com/'
# The regular feed contains summaries only; the full feed inlines content for
# items that AI HOT explicitly allows to be redistributed.
AIHOT_FEED_URL = urljoin(AIHOT_URL, 'feed/full.xml')
DEFAULT_COLLECTOR_PROXY_URL = 'http://127.0.0.1:7890'
DEFAULT_LLM_USER_AGENT = 'curl/8.5.0'
MIN_REWRITTEN_ARTICLE_LENGTH = 300


class FetchUrlError(Exception):
    """Raised when fetching a collector URL fails after configured retries."""


@dataclass(frozen=True)
class FeedConfig:
    url: str
    category: str = '文章'
    tags: tuple[str, ...] = ()


DEFAULT_TECH_FEED_CONFIGS = [
    FeedConfig('https://www.djangoproject.com/rss/weblog/', '后端开发', ('Python', 'Django', '后端')),
    FeedConfig('https://realpython.com/atom.xml', '后端开发', ('Python', '后端')),
    FeedConfig('https://blog.python.org/feeds/posts/default', '后端开发', ('Python', '后端')),
    FeedConfig('https://devblogs.microsoft.com/python/feed/', '后端开发', ('Python', '后端')),
    FeedConfig('https://go.dev/blog/feed.atom', '后端开发', ('Go', '后端')),
    FeedConfig('https://nodejs.org/en/feed/blog.xml', '后端开发', ('Node.js', 'JavaScript', '后端')),
    FeedConfig('https://blog.rust-lang.org/feed.xml', '后端开发', ('Rust', '系统编程', '后端')),
    FeedConfig('https://spring.io/blog.atom', '后端开发', ('Java', 'Spring', '后端')),
    FeedConfig('https://nextjs.org/feed.xml', '前端开发', ('Next.js', 'React', '前端')),
    FeedConfig('https://react.dev/rss.xml', '前端开发', ('React', '前端')),
    FeedConfig('https://blog.vuejs.org/feed.rss', '前端开发', ('Vue', '前端')),
    FeedConfig('https://devblogs.microsoft.com/typescript/feed/', '前端开发', ('TypeScript', '前端')),
    FeedConfig('https://developer.chrome.com/static/blog/feed.xml', '前端开发', ('Chrome', 'Web 性能', '前端')),
    FeedConfig('https://web.dev/static/blog/feed.xml', '前端开发', ('Web 性能', '前端')),
    FeedConfig('https://v8.dev/blog.atom', '前端开发', ('JavaScript', 'V8', '前端')),
    FeedConfig('https://kubernetes.io/feed.xml', '云原生', ('Kubernetes', '云原生')),
    FeedConfig('https://www.docker.com/feed/', '云原生', ('Docker', '云原生')),
    FeedConfig('https://www.cncf.io/blog/feed/', '云原生', ('CNCF', '云原生')),
    FeedConfig('https://istio.io/latest/feed.xml', '云原生', ('Istio', 'Service Mesh', '云原生')),
    FeedConfig('https://blog.cloudflare.com/rss/', '云平台', ('Cloudflare', '平台工程')),
    FeedConfig('https://aws.amazon.com/blogs/architecture/feed/', '架构设计', ('AWS', '架构设计')),
    FeedConfig('https://aws.amazon.com/blogs/machine-learning/feed/', 'AI 工程', ('AWS', 'AI', '机器学习')),
    FeedConfig('https://cloudblog.withgoogle.com/rss/', '云平台', ('GCP', '云平台')),
    FeedConfig('https://azure.microsoft.com/en-us/blog/feed/', '云平台', ('Azure', '云平台')),
    FeedConfig('https://planet.postgresql.org/rss20.xml', '数据库', ('PostgreSQL', '数据库')),
    FeedConfig('https://planetscale.com/blog/feed.atom', '数据库', ('MySQL', '数据库')),
    FeedConfig('https://www.percona.com/blog/feed/', '数据库', ('MySQL', '数据库')),
    FeedConfig('https://huggingface.co/blog/feed.xml', 'AI 工程', ('Hugging Face', 'AI', 'LLM')),
    FeedConfig('https://pytorch.org/blog/feed/', 'AI 工程', ('PyTorch', 'AI', '机器学习')),
    FeedConfig('https://blog.tensorflow.org/feeds/posts/default?alt=rss', 'AI 工程', ('TensorFlow', 'AI', '机器学习')),
    FeedConfig('https://openai.com/news/rss.xml', 'AI 工程', ('OpenAI', 'AI', 'LLM')),
    FeedConfig('https://feed.infoq.com/development/', '架构设计', ('InfoQ', '全栈')),
    FeedConfig('https://feed.infoq.com/ai-ml-data-eng/news/', 'AI 工程', ('InfoQ', 'AI', '数据工程')),
    FeedConfig('https://feed.infoq.com/devops/news/', '工程效能', ('DevOps', '工程效能')),
    FeedConfig('https://github.blog/engineering/feed/', '工程效能', ('GitHub', '工程效能', '平台工程')),
    FeedConfig('https://netflixtechblog.com/feed/', '架构设计', ('Netflix', '分布式系统', '架构设计')),
    FeedConfig('https://engineering.fb.com/feed/', '架构设计', ('Meta', '架构设计', '工程')),
    FeedConfig('https://engineering.atspotify.com/feed/', '架构设计', ('Spotify', '架构设计', '数据')),
    FeedConfig('https://slack.engineering/feed/', '工程效能', ('Slack', '工程效能', '平台工程')),
    FeedConfig('https://dropbox.tech/feed', '架构设计', ('Dropbox', '存储', '架构设计')),
    FeedConfig('https://medium.com/feed/airbnb-engineering', '前端开发', ('Airbnb', '前端', '工程实践')),
    FeedConfig('https://tech.meituan.com/rss.xml', '全栈实践', ('美团', '工程实践', '全栈')),
    FeedConfig('https://www.ruanyifeng.com/blog/atom.xml', '全栈实践', ('阮一峰', '全栈', '技术趋势')),
    FeedConfig('https://www.oschina.net/news/rss', '全栈实践', ('开源中国', '全栈', '开源')),
]
DEFAULT_TECH_FEEDS = [config.url for config in DEFAULT_TECH_FEED_CONFIGS]
TECH_ARTICLE_WRITER_SKILL_PATH = (
    Path(__file__).resolve().parents[1]
    / 'skills'
    / 'technical_article_writer'
    / 'SKILL.md'
)


@dataclass
class CollectorResult:
    created: int = 0
    skipped: int = 0
    failed: int = 0
    created_articles: list = None

    def __post_init__(self):
        if self.created_articles is None:
            self.created_articles = []


TAG_KEYWORDS = {
    'React': ('react',),
    'Vue': ('vue',),
    'Next.js': ('next.js', 'nextjs'),
    'TypeScript': ('typescript',),
    'JavaScript': ('javascript',),
    'Go': ('go', 'golang'),
    'Python': ('python',),
    'Django': ('django',),
    'Java': ('java', 'spring'),
    'Rust': ('rust',),
    'Kubernetes': ('kubernetes', 'k8s'),
    'Docker': ('docker',),
    'PostgreSQL': ('postgresql',),
    'MySQL': ('mysql',),
    'Redis': ('redis',),
    'OpenAI': ('openai',),
    'LLM': ('llm', 'rag', 'agent'),
    'PyTorch': ('pytorch',),
    'TensorFlow': ('tensorflow',),
    'Cloudflare': ('cloudflare',),
    'AWS': ('aws',),
    'GCP': ('gcp', 'google cloud'),
    'Azure': ('azure',),
}


def fetch_url(url, timeout=20):
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; BlogCollector/1.0; +https://github.com/jeffryqueenie-coder/djangoblog)'
    }
    try:
        return request_url(url, headers=headers, timeout=timeout)
    except requests.RequestException as direct_error:
        proxy_url = get_collector_proxy_url()
        if not proxy_url:
            raise FetchUrlError(
                f'direct failed ({summarize_request_error(direct_error)})'
            ) from None

        try:
            return request_url(
                url,
                headers=headers,
                timeout=timeout,
                proxies=build_proxy_config(proxy_url),
            )
        except requests.RequestException as proxy_error:
            raise FetchUrlError(
                'direct failed '
                f'({summarize_request_error(direct_error)}); '
                f'proxy {proxy_url} failed ({summarize_request_error(proxy_error)})'
            ) from None


def request_url(url, headers, timeout, proxies=None):
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(url, headers=headers, timeout=timeout, proxies=proxies)
    response.raise_for_status()
    return response.text


def get_collector_proxy_url():
    return os.environ.get('COLLECTOR_PROXY_URL', DEFAULT_COLLECTOR_PROXY_URL).strip()


def build_proxy_config(proxy_url):
    return {
        'http': proxy_url,
        'https': proxy_url,
    }


def summarize_request_error(error):
    if isinstance(error, requests.HTTPError) and error.response is not None:
        response = error.response
        return f'{type(error).__name__}: HTTP {response.status_code} {response.reason}'
    return f'{type(error).__name__}: {error}'


def summarize_exception(error):
    return f'{type(error).__name__}: {error}'


def should_log_collector_tracebacks():
    return bool(
        getattr(settings, 'DEBUG', False)
        or getattr(settings, 'COLLECTOR_LOG_TRACEBACKS', False)
    )


def parse_aihot_items(html, base_url=AIHOT_URL):
    soup = BeautifulSoup(html, 'html.parser')
    cards = soup.select('article, [class*="card"], [class*="item"], li')
    seen = set()
    items = []

    for card in cards:
        link = card.find('a', href=True)
        if not link:
            continue
        href = urljoin(base_url, link['href'])
        title = normalize_text(link.get_text(' ', strip=True))
        if not title or href in seen or len(title) < 4:
            continue

        text = normalize_text(card.get_text(' ', strip=True))
        summary = text.replace(title, '', 1).strip()
        tags = normalize_news_tags(
            normalize_text(tag.get_text(' ', strip=True))
            for tag in card.select('[class*="tag"], .badge')
        )
        items.append({
            'title': title[:300],
            'summary': summary[:1200],
            'reason': '',
            'source': 'aihot',
            'source_name': 'AI HOT',
            'source_url': href,
            'tags': ','.join(tags)[:300],
            'published_at': timezone.now(),
        })
        seen.add(href)

    return items


def parse_aihot_feed(xml_text):
    root = ET.fromstring(xml_text)
    items = []

    for node in root.findall('.//channel/item'):
        title = normalize_text(child_text(node, 'title'))
        source_url = normalize_text(child_text(node, 'link'))
        if not title or not source_url:
            continue

        description = child_text(node, 'description')
        summary, original_url = parse_aihot_description(description, source_url)
        author = child_text(node, 'author')
        source_name_match = re.search(r'\((.+)\)\s*$', author)
        content = clean_aihot_content(child_text(node, 'encoded'), source_url)

        item = {
            'title': title[:300],
            'summary': summary[:1200],
            'source': 'aihot',
            'source_name': normalize_text(
                source_name_match.group(1) if source_name_match else author
            )[:120],
            'source_url': source_url,
            'original_url': original_url[:1000],
            'tags': normalize_text(child_text(node, 'category'))[:300],
            'published_at': normalize_model_datetime(
                parse_datetime(child_text(node, 'pubDate'))
            ),
        }
        if content:
            item['content'] = content
        items.append(item)

    return items


def parse_aihot_description(description, base_url=AIHOT_URL):
    """Extract plain summary text and the original link from AI HOT HTML."""
    raw_description = description or ''
    soup = BeautifulSoup(raw_description, 'html.parser')
    original_url = ''

    for link in soup.find_all('a', href=True):
        if '阅读原文' in normalize_text(link.get_text(' ', strip=True)):
            original_url = urljoin(base_url, link['href']).strip()
            break

    # AI HOT appends these metadata paragraphs after the actual summary.
    for element in soup.find_all(['p', 'li']):
        text = normalize_text(element.get_text(' ', strip=True))
        if '阅读原文' in text or re.match(r'^via\s+AI\s*HOT\b', text, re.I):
            element.decompose()

    plain_text = normalize_text(soup.get_text(' ', strip=True))
    plain_text = re.sub(r'\s+([,.;:!?，。；：！？])', r'\1', plain_text)
    if not original_url:
        original_url_match = re.search(
            r'阅读原文[：:]\s*(https?://\S+)',
            plain_text,
        )
        if original_url_match:
            original_url = original_url_match.group(1).rstrip('。.,，')

    summary = re.split(
        r'\s+(?:🔗\s*)?阅读原文[：:]\s*https?://\S+|\s+via\s+AI\s*HOT\b.*$',
        plain_text,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    return summary[:1200], original_url


def clean_aihot_content(content, base_url=AIHOT_URL):
    if not content:
        return ''

    soup = BeautifulSoup(content, 'html.parser')
    for element in soup.select('script, style'):
        element.decompose()
    for paragraph in soup.find_all('p'):
        if '本文由 AI HOT 聚合整理' in paragraph.get_text(' ', strip=True):
            paragraph.decompose()
    for element in soup.find_all(href=True):
        element['href'] = urljoin(base_url, element['href'])
        element['rel'] = 'noopener nofollow'
    for element in soup.find_all(src=True):
        element['src'] = urljoin(base_url, element['src'])
    return sanitize_html(str(soup)).strip()


def normalize_news_tags(tags):
    normalized = []
    for tag in tags:
        tag = normalize_text(tag)
        if tag and tag not in normalized:
            normalized.append(tag)

    atomic_tags = []
    for tag in normalized:
        is_joined_duplicate = any(
            tag != other and re.search(rf'(^|\s){re.escape(other)}($|\s)', tag)
            for other in normalized
        )
        if not is_joined_duplicate:
            atomic_tags.append(tag)
    return atomic_tags


def collect_aihot_news(limit=30, hours=None):
    result = CollectorResult()
    try:
        xml_text = fetch_url(AIHOT_FEED_URL)
    except FetchUrlError as error:
        logger.error('Failed to fetch AI HOT news: %s', error)
        result.failed += 1
        return result

    try:
        items = parse_aihot_feed(xml_text)[:limit]
    except Exception as error:
        logger.error('Failed to parse AI HOT feed: %s', summarize_exception(error))
        result.failed += 1
        return result
    cutoff = timezone.now() - timezone.timedelta(hours=hours) if hours else None

    for item in items:
        if cutoff and item.get('published_at') and item['published_at'] < cutoff:
            result.skipped += 1
            continue
        try:
            source_url_hash = hash_url(item['source_url'])
            existing = NewsItem.objects.filter(
                source_url_hash=source_url_hash,
            ).only('content', 'tags').first()
            if not existing and item.get('original_url'):
                existing = NewsItem.objects.filter(
                    Q(original_url=item['original_url'])
                    | Q(source_url=item['original_url'])
                ).only('content', 'tags').first()
            if existing and existing.content and not item.get('content'):
                item['content'] = existing.content
            if existing and existing.tags:
                item['tags'] = existing.tags

            if existing:
                for field, value in item.items():
                    setattr(existing, field, value)
                existing.save()
                created = False
            else:
                NewsItem.objects.create(**item)
                created = True
            if created:
                result.created += 1
            else:
                result.skipped += 1
        except Exception as error:
            logger.error(
                'Failed to store AI HOT news %s: %s',
                item.get('source_url'),
                summarize_exception(error),
                exc_info=should_log_collector_tracebacks(),
            )
            result.failed += 1

    cache.clear()
    return result


def parse_feed_entries(xml_text, source_url):
    root = ET.fromstring(xml_text)
    entries = []

    if root.tag.endswith('rss'):
        channel = root.find('.//channel')
        source_name = child_text(channel, 'title') if channel is not None else source_url
        for item in root.findall('.//channel/item'):
            entries.append({
                'title': normalize_text(child_text(item, 'title')),
                'url': normalize_text(child_text(item, 'link')),
                'summary': strip_html(child_text(item, 'description')),
                'published_at': parse_datetime(child_text(item, 'pubDate')),
                'source_name': source_name or source_url,
            })
        return entries

    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    source_name = child_text(root, 'title') or source_url
    for entry in root.findall('.//atom:entry', ns):
        link = entry.find('atom:link[@rel="alternate"]', ns) or entry.find('atom:link', ns)
        entries.append({
            'title': normalize_text(child_text(entry, 'title')),
            'url': normalize_text(link.get('href') if link is not None else ''),
            'summary': strip_html(child_text(entry, 'summary') or child_text(entry, 'content')),
            'published_at': parse_datetime(child_text(entry, 'updated') or child_text(entry, 'published')),
            'source_name': source_name,
        })
    return entries


def collect_tech_articles(limit=5, feeds=None, hours=None):
    feed_configs = normalize_feed_configs(feeds or parse_feed_list())
    cutoff = timezone.now() - timezone.timedelta(hours=hours) if hours else None
    result = CollectorResult()
    entries_by_url = {}

    for feed in feed_configs:
        try:
            xml_text = fetch_url(feed.url)
        except FetchUrlError as error:
            logger.error('Failed to fetch feed %s: %s', feed.url, error)
            result.failed += 1
            continue

        try:
            entries = parse_feed_entries(xml_text, feed.url)
        except Exception as error:
            logger.error('Failed to parse feed %s: %s', feed.url, error)
            result.failed += 1
            continue

        for entry in entries:
            if not entry['title'] or not entry['url']:
                result.skipped += 1
                continue
            published_at = entry_published_at(entry)
            if is_before_cutoff(published_at, cutoff):
                result.skipped += 1
                continue
            entry['published_at'] = published_at
            entry['feed_category'] = feed.category
            entry['feed_tags'] = feed.tags
            entries_by_url.setdefault(entry['url'], entry)

    for entry in sort_feed_entries(entries_by_url.values()):
        if result.created >= limit:
            break
        if Article.objects.filter(body__contains=entry['url']).exists():
            result.skipped += 1
            continue
        rewritten = rewrite_article(entry)
        if not rewritten:
            result.skipped += 1
            continue
        if not is_publishable_rewrite(rewritten):
            logger.warning('Skipping article with invalid or incomplete rewrite: %s', entry['url'])
            result.skipped += 1
            continue
        try:
            article = publish_rewritten_article(entry, rewritten)
            result.created_articles.append(article)
            result.created += 1
        except IntegrityError:
            result.skipped += 1
        except Exception as error:
            logger.error(
                'Failed to publish rewritten article %s: %s',
                entry['url'],
                summarize_exception(error),
                exc_info=should_log_collector_tracebacks(),
            )
            result.failed += 1

    cache.clear()
    return result


def rewrite_article(entry):
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return ''

    try:
        from openai import OpenAI
        user_agent = (
            os.environ.get('OPENAI_USER_AGENT', DEFAULT_LLM_USER_AGENT).strip()
            or DEFAULT_LLM_USER_AGENT
        )
        client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get('OPENAI_BASE_URL') or None,
            default_headers={'User-Agent': user_agent},
        )
        response = client.chat.completions.create(
            model=os.environ.get('BLOG_LLM_MODEL', 'gpt-4o-mini'),
            messages=[
                {
                    'role': 'system',
                    'content': load_technical_writer_skill(),
                },
                {
                    'role': 'user',
                    'content': (
                        f"来源标题：{entry['title']}\n"
                        f"来源摘要：{entry['summary']}\n\n"
                        "请输出一个 JSON 对象，不要输出 Markdown fence。字段必须为：\n"
                        "- title_zh: 中文标题\n"
                        "- body_zh: 完整中文 Markdown 正文\n"
                        "- title_en: English title\n"
                        "- body_en: Complete English Markdown body\n"
                        "- seo_description_en: English SEO summary within 160 characters\n\n"
                        "中文正文仍需符合 skill 要求，必须包含至少一个和主题相关、可复制运行或改造的代码/命令/YAML 示例。"
                        "英文正文应表达同一篇文章的英文版本，不要逐字僵硬翻译。"
                        "不要包含原文链接，发布流水线会追加来源链接。"
                    )
                },
            ],
            temperature=0.4,
        )
        if getattr(response, 'usage', None):
            logger.info(
                'LLM usage for %s: prompt=%s completion=%s total=%s',
                entry.get('url'),
                getattr(response.usage, 'prompt_tokens', None),
                getattr(response.usage, 'completion_tokens', None),
                getattr(response.usage, 'total_tokens', None),
            )
        return parse_rewritten_article(response.choices[0].message.content.strip())
    except Exception as error:
        logger.error(
            'Failed to rewrite article with LLM %s: %s',
            entry.get('url'),
            summarize_exception(error),
            exc_info=should_log_collector_tracebacks(),
        )
        return {}


def parse_rewritten_article(content):
    raw = (content or '').strip()
    if not raw:
        return {}
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.I)
        raw = re.sub(r'\s*```$', '', raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # The collector asks for a JSON object. A malformed object usually means
        # an unescaped quote in generated code; publishing it as Markdown exposes
        # the whole broken payload to readers.
        if raw.startswith('{'):
            logger.warning('Discarding malformed JSON response from article writer')
            return {}
        title = extract_markdown_title(raw)
        body = strip_leading_markdown_title(raw, title) if title else raw
        return {
            'title_zh': title,
            'body_zh': body,
            'title_en': '',
            'body_en': '',
            'seo_description_en': '',
        }
    return normalize_rewritten_article(data)


def normalize_rewritten_article(rewritten):
    if isinstance(rewritten, str):
        title = extract_markdown_title(rewritten)
        body = strip_leading_markdown_title(rewritten, title) if title else rewritten
        return {
            'title_zh': title,
            'body_zh': body,
            'title_en': '',
            'body_en': '',
            'seo_description_en': '',
        }
    if not isinstance(rewritten, dict):
        return {}
    return {
        'title_zh': normalize_text(rewritten.get('title_zh') or rewritten.get('title') or ''),
        'body_zh': (rewritten.get('body_zh') or rewritten.get('body') or '').strip(),
        'title_en': normalize_text(rewritten.get('title_en') or ''),
        'body_en': (rewritten.get('body_en') or '').strip(),
        'seo_description_en': normalize_text(rewritten.get('seo_description_en') or '')[:300],
    }


def is_publishable_rewrite(rewritten):
    normalized = normalize_rewritten_article(rewritten)
    title = normalized.get('title_zh') or extract_markdown_title(
        normalized.get('body_zh') or ''
    )
    body = strip_source_link_lines(normalized.get('body_zh') or '')
    body = strip_leading_markdown_title(body, title)

    return bool(
        title
        and len(body) >= MIN_REWRITTEN_ARTICLE_LENGTH
        and re.search(r'^##\s+\S+', body, flags=re.M)
        and '```' in body
    )


def publish_rewritten_article(entry, rewritten):
    rewritten = normalize_rewritten_article(rewritten)
    if not rewritten.get('body_zh'):
        raise ValueError('Rewritten article is missing body_zh')
    category_name, tag_names = determine_article_taxonomy(entry)
    category, _ = Category.objects.get_or_create(name=category_name)
    if category.name == '文章' and not category.name_en:
        category.name_en = 'Articles'
        category.save(update_fields=['name_en', 'last_modify_time'])
    author = get_default_author()
    body = strip_source_link_lines(rewritten['body_zh'])
    title = rewritten.get('title_zh') or extract_markdown_title(body) or entry['title']
    body = strip_leading_markdown_title(body, title)
    body_en = strip_source_link_lines(rewritten.get('body_en') or '')
    title_en = rewritten.get('title_en') or extract_markdown_title(body_en)
    if title_en:
        body_en = strip_leading_markdown_title(body_en, title_en)
    pub_time = clamp_future_pub_time(normalize_model_datetime(entry['published_at']))
    article = Article.objects.create(
        title=title[:200],
        body=append_source_link(body, entry['url']),
        title_en=title_en[:200],
        body_en=body_en,
        seo_description_en=rewritten.get('seo_description_en', ''),
        pub_time=pub_time or timezone.now(),
        status='p',
        type='a',
        comment_status='c',
        author=author,
        category=category,
    )
    for tag_name in tag_names:
        tag, _ = Tag.objects.get_or_create(name=tag_name[:30])
        article.tags.add(tag)
    return article


def load_technical_writer_skill():
    try:
        return TECH_ARTICLE_WRITER_SKILL_PATH.read_text(encoding='utf-8')
    except OSError:
        logger.warning('Technical writer skill not found: %s', TECH_ARTICLE_WRITER_SKILL_PATH)
        return (
            '你是技术博客作者。基于给定信息写一篇中文技术文章。'
            '输出 Markdown，包含具体分析和至少一个可复制的代码或命令示例。'
            '不能编造来源没有的信息，不要输出原文链接。'
        )


def get_default_author():
    User = get_user_model()
    user = User.objects.filter(is_superuser=True).first() or User.objects.first()
    if user:
        return user
    return User.objects.create_superuser('admin', 'admin@example.com', 'admin123')


def run_collectors_loop(interval=1800):
    while True:
        news_result = collect_aihot_news(
            limit=get_env_int('AIHOT_NEWS_LIMIT', 30),
            hours=get_optional_env_int('AIHOT_NEWS_LOOKBACK_HOURS'),
        )
        article_result = collect_tech_articles(
            limit=get_env_int('TECH_ARTICLE_LIMIT', 5),
            hours=get_optional_env_int('TECH_ARTICLE_LOOKBACK_HOURS'),
        )
        logger.info(
            'Collectors finished: news created=%s skipped=%s failed=%s; articles created=%s skipped=%s failed=%s',
            news_result.created,
            news_result.skipped,
            news_result.failed,
            article_result.created,
            article_result.skipped,
            article_result.failed,
        )
        if article_result.created_articles:
            notify_indexnow_articles(article_result.created_articles)
        time.sleep(interval)


def parse_feed_list():
    return [config.url for config in parse_feed_configs()]


def parse_feed_configs():
    raw = os.environ.get('TECH_BLOG_FEEDS', '')
    extra_raw = os.environ.get('TECH_BLOG_EXTRA_FEEDS', '')
    if raw:
        configs = normalize_feed_configs([item.strip() for item in raw.split(',') if item.strip()])
    else:
        configs = list(DEFAULT_TECH_FEED_CONFIGS)
    if extra_raw:
        configs.extend(
            normalize_feed_configs([item.strip() for item in extra_raw.split(',') if item.strip()])
        )
    return deduplicate_feed_configs(configs)


def normalize_feed_configs(feeds):
    configs = []
    for feed in feeds:
        if isinstance(feed, FeedConfig):
            configs.append(feed)
            continue
        matched = next((item for item in DEFAULT_TECH_FEED_CONFIGS if item.url == feed), None)
        if matched:
            configs.append(matched)
        else:
            configs.append(FeedConfig(feed))
    return configs


def deduplicate_feed_configs(configs):
    deduped = []
    seen = set()
    for config in configs:
        if config.url in seen:
            continue
        deduped.append(config)
        seen.add(config.url)
    return deduped


def determine_article_taxonomy(entry):
    feed_tags = tuple(dict.fromkeys(entry.get('feed_tags') or ()))
    combined_text = ' '.join(
        filter(
            None,
            [
                entry.get('title') or '',
                entry.get('summary') or '',
                entry.get('source_name') or '',
                ' '.join(feed_tags),
            ],
        )
    ).lower()

    category_name = '文章'
    detected_tags = list(feed_tags)
    for tag_name, keywords in TAG_KEYWORDS.items():
        if any(keyword in combined_text for keyword in keywords):
            detected_tags.append(tag_name)
    detected_tags.extend(default_tags_for_entry(combined_text))
    return category_name, tuple(dict.fromkeys(tag for tag in detected_tags if tag))


def default_tags_for_entry(text):
    defaults = []
    if any(keyword in text for keyword in ('react', 'vue', 'next.js', 'nextjs', 'typescript', 'javascript', 'css', 'web', '浏览器', 'chrome', '前端')):
        defaults.append('前端')
    if any(keyword in text for keyword in ('go', 'golang', 'python', 'django', 'flask', 'fastapi', 'java', 'spring', 'node', 'node.js', 'api', 'server', '后端')):
        defaults.append('后端')
    if any(keyword in text for keyword in ('kubernetes', 'docker', 'container', 'helm', 'istio', 'service mesh', 'cloud native', '云原生')):
        defaults.append('云原生')
    if any(keyword in text for keyword in ('postgresql', 'mysql', 'redis', 'sql', 'database', '数据库', '缓存')):
        defaults.append('数据库')
    if any(keyword in text for keyword in ('openai', 'llm', 'rag', 'hugging face', 'pytorch', 'tensorflow', 'model', '模型', '推理', 'agent', 'ai')):
        defaults.append('AI')
    if any(keyword in text for keyword in ('architecture', 'scaling', 'distributed', 'microservice', '系统设计', '架构', '分布式', '可扩展')):
        defaults.append('架构设计')
    if any(keyword in text for keyword in ('ci/cd', 'cicd', 'devops', 'testing', 'observability', 'platform', '工程效率', '工程效能', '测试')):
        defaults.append('工程效能')
    if any(keyword in text for keyword in ('security', 'trace', 'tracing', 'monitoring', 'otel', '安全', '监控')):
        defaults.extend(['安全', '可观测性'])
    if any(keyword in text for keyword in ('aws', 'gcp', 'azure', 'cloudflare', 'serverless', '云平台')):
        defaults.append('云平台')
    if any(keyword in text for keyword in ('全栈', '实践', 'product engineering', 'engineering', '开发者体验', 'dx')):
        defaults.append('全栈')
    return tuple(dict.fromkeys(defaults))


def sort_feed_entries(entries):
    return sorted(entries, key=feed_entry_timestamp, reverse=True)


def feed_entry_timestamp(entry):
    published_at = entry_published_at(entry)
    if not published_at:
        return 0
    return published_at.timestamp()


def entry_published_at(entry):
    return normalize_aware_datetime(entry.get('published_at'))


def is_before_cutoff(value, cutoff):
    value = normalize_naive_datetime(value)
    cutoff = normalize_naive_datetime(cutoff)
    return bool(value and cutoff and value < cutoff)


def normalize_naive_datetime(value):
    if value is None:
        return None
    if timezone.is_aware(value):
        return timezone.make_naive(value, timezone.get_current_timezone())
    return value


def normalize_aware_datetime(value):
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def get_env_int(name, default):
    value = os.environ.get(name)
    if value in (None, ''):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        logger.warning('Invalid integer env %s=%r, using %s', name, value, default)
        return default
    return parsed if parsed > 0 else default


def get_optional_env_int(name):
    value = os.environ.get(name)
    if value in (None, ''):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        logger.warning('Invalid integer env %s=%r, ignoring it', name, value)
        return None
    return parsed if parsed > 0 else None


def child_text(node, name):
    child = node.find(name)
    if child is not None and child.text:
        return child.text.strip()
    for child in list(node):
        if child.tag.endswith(name) and child.text:
            return child.text.strip()
    return ''


def parse_datetime(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        try:
            parsed = timezone.datetime.fromisoformat(value.replace('Z', '+00:00'))
        except Exception:
            return None
    return normalize_aware_datetime(parsed)


def strip_html(value):
    return normalize_text(BeautifulSoup(value or '', 'html.parser').get_text(' ', strip=True))


def normalize_text(value):
    return re.sub(r'\s+', ' ', unescape(value or '')).strip()


def hash_url(url):
    return hashlib.sha256(url.encode('utf-8')).hexdigest()


def normalize_model_datetime(value):
    if value is None:
        return None
    if timezone.is_aware(value):
        return timezone.make_naive(value, timezone.get_current_timezone())
    return value


def clamp_future_pub_time(value):
    if value is None:
        return None
    now_value = normalize_model_datetime(timezone.now()) or timezone.now()
    if value > now_value:
        return now_value
    return value


def strip_source_link_lines(body):
    lines = []
    for line in body.splitlines():
        normalized = line.strip().lower()
        if re.search(r'\[?原文链接\]?|原文[:：]|source\s*link|original\s*link', normalized):
            continue
        lines.append(line)
    return '\n'.join(lines).strip()


def extract_source_url(body):
    for line in reversed(body.splitlines()):
        markdown_match = re.search(r'\[原文链接\]\((https?://[^)\s]+)\)', line)
        if markdown_match:
            return markdown_match.group(1)
        plain_match = re.search(r'原文链接[:：]\s*(https?://\S+)', line)
        if plain_match:
            return plain_match.group(1).rstrip('。.,，')
    return ''


def append_source_link(body, url):
    body = strip_source_link_lines(body)
    if not url:
        return body
    return f"{body}\n\n---\n[原文链接]({url})"


def extract_markdown_title(body):
    for line in body.splitlines():
        match = re.match(r'^\s*#\s+(.+?)\s*#*\s*$', line)
        if match:
            return normalize_text(match.group(1))
    return ''


def strip_leading_markdown_title(body, title):
    lines = body.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and re.match(r'^\s*#\s+', lines[0]):
        heading = normalize_text(re.sub(r'^\s*#\s+', '', lines[0]).strip(' #'))
        if not title or heading == title:
            lines.pop(0)
    return '\n'.join(lines).strip()
