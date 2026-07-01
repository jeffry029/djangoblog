from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests

from django.http import Http404
from django.test import Client, RequestFactory, SimpleTestCase, override_settings

from djangoblog.indexnow import notify_indexnow_urls
from djangoblog.urls import indexnow_key_file


class IndexNowKeyFileTest(SimpleTestCase):
    def test_indexnow_key_file_is_served_from_site_root(self):
        with TemporaryDirectory() as tmpdir:
            key = 'abc12345'
            key_path = Path(tmpdir) / f'{key}.txt'
            key_path.write_text(key, encoding='utf-8')

            with override_settings(INDEXNOW_KEY=key, INDEXNOW_KEY_FILE_PATH=str(key_path)):
                response = Client().get(f'/{key}.txt')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertEqual(response.content.decode('utf-8'), key)

    def test_wrong_indexnow_key_file_returns_404(self):
        with override_settings(INDEXNOW_KEY='abc12345'):
            request = RequestFactory().get('/wrongkey1.txt')

            with self.assertRaises(Http404):
                indexnow_key_file(request, 'wrongkey1')


class IndexNowNotifyTest(SimpleTestCase):
    @override_settings(
        INDEXNOW_KEY='abc12345',
        INDEXNOW_HOST='www.example.org',
        INDEXNOW_KEY_LOCATION='',
        INDEXNOW_ENDPOINT='https://api.indexnow.org/indexnow',
        INDEXNOW_REQUEST_TIMEOUT=5,
    )
    @patch('djangoblog.indexnow.requests.post')
    def test_notify_indexnow_urls_posts_deduplicated_payload(self, post):
        response = post.return_value
        response.status_code = 202
        response.raise_for_status.return_value = None

        ok = notify_indexnow_urls([
            'https://www.example.org/url1',
            'https://www.example.org/url1',
            '',
            'https://www.example.org/url2',
        ])

        self.assertTrue(ok)
        post.assert_called_once_with(
            'https://api.indexnow.org/indexnow',
            json={
                'host': 'www.example.org',
                'key': 'abc12345',
                'keyLocation': 'https://www.example.org/abc12345.txt',
                'urlList': [
                    'https://www.example.org/url1',
                    'https://www.example.org/url2',
                ],
            },
            headers={'Content-Type': 'application/json; charset=utf-8'},
            timeout=5,
        )

    @override_settings(
        DEBUG=False,
        COLLECTOR_LOG_TRACEBACKS=False,
        INDEXNOW_KEY='abc12345',
        INDEXNOW_HOST='www.example.org',
        INDEXNOW_ENDPOINT='https://api.indexnow.org/indexnow',
    )
    @patch('djangoblog.indexnow.logger')
    @patch('djangoblog.indexnow.requests.post')
    def test_notify_indexnow_failure_logs_without_traceback_by_default(self, post, logger_mock):
        post.side_effect = requests.Timeout('timeout')

        ok = notify_indexnow_urls(['https://www.example.org/url1'])

        self.assertFalse(ok)
        self.assertFalse(logger_mock.warning.call_args.kwargs['exc_info'])
