from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from blog.models import PublicTrafficDailyStat
from djangoblog.test_base import BaseTestCase


BROWSER_META = {
    'HTTP_USER_AGENT': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'
    ),
    'HTTP_ACCEPT': 'text/html,application/xhtml+xml',
    'REMOTE_ADDR': '203.0.113.10',
}


@override_settings(
    PUBLIC_READ_ONLY_MODE=True,
    PUBLIC_RATE_LIMIT_PER_MINUTE=0,
    PUBLIC_LIST_RATE_LIMIT_PER_MINUTE=0,
    PUBLIC_FINGERPRINT_RATE_LIMIT_PER_MINUTE=0,
)
class PublicTrafficRecordingTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_browser_request_records_daily_visit_and_increments_repeat(self):
        self.client.get(reverse('blog:news'), **BROWSER_META)
        self.client.get(reverse('blog:news'), **BROWSER_META)

        stat = PublicTrafficDailyStat.objects.get(
            date=timezone.now().date(),
            route_name='news',
            path='/news/',
            ip_address='203.0.113.10',
        )
        self.assertEqual(stat.visit_count, 2)
        self.assertIn('Chrome', stat.user_agent)

    def test_script_request_is_not_counted_as_real_browser_visit(self):
        self.client.get(
            reverse('blog:news'),
            HTTP_USER_AGENT='python-requests/2.31',
            HTTP_ACCEPT='*/*',
            REMOTE_ADDR='203.0.113.11',
        )

        self.assertFalse(PublicTrafficDailyStat.objects.exists())

    @override_settings(PUBLIC_TRAFFIC_STATS_TOKEN='secret-token')
    def test_internal_stats_endpoint_requires_token(self):
        response = self.client.get('/_internal/traffic-stats/')

        self.assertEqual(response.status_code, 404)

    @override_settings(PUBLIC_TRAFFIC_STATS_TOKEN='secret-token')
    def test_internal_stats_endpoint_returns_date_filtered_counts(self):
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        PublicTrafficDailyStat.objects.create(
            date=today,
            route_name='news',
            path='/news/',
            ip_address='203.0.113.10',
            fingerprint='today-fingerprint',
            user_agent='Mozilla/5.0 Chrome/125.0',
            visit_count=3,
        )
        PublicTrafficDailyStat.objects.create(
            date=yesterday,
            route_name='index',
            path='/',
            ip_address='203.0.113.10',
            fingerprint='yesterday-fingerprint',
            user_agent='Mozilla/5.0 Chrome/125.0',
            visit_count=7,
        )

        response = self.client.get(
            '/_internal/traffic-stats/',
            {'token': 'secret-token', 'date': today.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['total_visits'], 3)
        self.assertEqual(len(data['rows']), 1)
        self.assertEqual(data['rows'][0]['route_name'], 'news')


class PublicTrafficModelImportTests(TestCase):
    def test_model_is_available_for_import(self):
        self.assertEqual(PublicTrafficDailyStat.__name__, 'PublicTrafficDailyStat')
