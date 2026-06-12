import logging
from urllib.parse import urlparse

import requests
from django.conf import settings

from djangoblog.utils import get_current_site

logger = logging.getLogger(__name__)


def get_indexnow_key():
    return (getattr(settings, 'INDEXNOW_KEY', '') or '').strip()


def get_indexnow_host():
    configured_host = (getattr(settings, 'INDEXNOW_HOST', '') or '').strip()
    site_domain = configured_host or get_current_site().domain
    parsed = urlparse(site_domain if '://' in site_domain else f'https://{site_domain}')
    return parsed.netloc or parsed.path


def get_indexnow_key_location():
    configured_location = (getattr(settings, 'INDEXNOW_KEY_LOCATION', '') or '').strip()
    if configured_location:
        return configured_location
    key = get_indexnow_key()
    host = get_indexnow_host()
    return f'https://{host}/{key}.txt'


def build_indexnow_payload(urls):
    normalized_urls = list(dict.fromkeys(url for url in urls if url))
    return {
        'host': get_indexnow_host(),
        'key': get_indexnow_key(),
        'keyLocation': get_indexnow_key_location(),
        'urlList': normalized_urls[:10000],
    }


def notify_indexnow_urls(urls):
    key = get_indexnow_key()
    normalized_urls = list(dict.fromkeys(url for url in urls if url))
    if not key or not normalized_urls:
        return False

    payload = build_indexnow_payload(normalized_urls)
    endpoint = getattr(settings, 'INDEXNOW_ENDPOINT', 'https://api.indexnow.org/indexnow')
    timeout = getattr(settings, 'INDEXNOW_REQUEST_TIMEOUT', 10)

    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers={'Content-Type': 'application/json; charset=utf-8'},
            timeout=timeout,
        )
        response.raise_for_status()
        logger.info('IndexNow notified %s urls: %s', len(payload['urlList']), response.status_code)
        return True
    except Exception:
        logger.exception('Failed to notify IndexNow')
        return False


def notify_indexnow_articles(articles):
    urls = [
        article.get_full_url()
        for article in articles
        if getattr(article, 'status', None) == 'p' and getattr(article, 'type', None) == 'a'
    ]
    return notify_indexnow_urls(urls)
