import hashlib
import ipaddress
import logging

from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone

from blog.models import PublicTrafficDailyStat

logger = logging.getLogger(__name__)

WATCHED_ROUTE_PREFIXES = (
    ('news', '/news/'),
    ('search', '/search'),
    ('index_page', '/page/'),
)

BROWSER_MARKERS = (
    'mozilla/',
    'chrome/',
    'safari/',
    'firefox/',
    'edg/',
)

SCRIPT_MARKERS = (
    'bot',
    'spider',
    'crawler',
    'curl',
    'python-requests',
    'wget',
    'httpclient',
    'scrapy',
    'headless',
)


def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        ip = forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '') or '0.0.0.0'

    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return '0.0.0.0'


def route_name_for_path(path):
    if path == '/':
        return 'index'

    normalized_path = path if path.endswith('/') else f'{path}/'
    for route_name, prefix in WATCHED_ROUTE_PREFIXES:
        if normalized_path.startswith(prefix):
            return route_name
    return ''


def is_watched_public_route(request):
    return bool(route_name_for_path(request.path_info))


def request_fingerprint(request):
    raw = '|'.join([
        request.path_info,
        request.META.get('QUERY_STRING', ''),
        request.META.get('HTTP_USER_AGENT', ''),
    ])
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def looks_like_browser(request):
    if request.method.upper() not in {'GET', 'HEAD'}:
        return False

    if not is_watched_public_route(request):
        return False

    accept = request.META.get('HTTP_ACCEPT', '').lower()
    if 'text/html' not in accept and '*/*' not in accept:
        return False

    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    if not user_agent:
        return False
    if any(marker in user_agent for marker in SCRIPT_MARKERS):
        return False
    return any(marker in user_agent for marker in BROWSER_MARKERS)


def record_public_visit(request):
    if not looks_like_browser(request):
        return False

    now = timezone.now()
    defaults = {
        'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
        'visit_count': 1,
        'first_seen': now,
        'last_seen': now,
    }
    identity = {
        'date': now.date(),
        'route_name': route_name_for_path(request.path_info),
        'path': request.path_info[:255],
        'ip_address': get_client_ip(request),
        'fingerprint': request_fingerprint(request),
    }

    try:
        stat, created = PublicTrafficDailyStat.objects.get_or_create(
            **identity,
            defaults=defaults,
        )
        if created:
            return True
        PublicTrafficDailyStat.objects.filter(pk=stat.pk).update(
            visit_count=F('visit_count') + 1,
            user_agent=defaults['user_agent'],
            last_seen=now,
        )
        return True
    except IntegrityError:
        PublicTrafficDailyStat.objects.filter(**identity).update(
            visit_count=F('visit_count') + 1,
            user_agent=defaults['user_agent'],
            last_seen=now,
        )
        return True
    except Exception:
        logger.exception('Failed to record public traffic')
        return False
