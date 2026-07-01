from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.urls.exceptions import Resolver404

from djangoblog.error_views import render_error_page


class ErrorViewLoggingTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_4xx_errors_log_short_debug_without_traceback(self):
        request = self.factory.get('/wp-admin/install.php')
        exception = Resolver404({'path': 'wp-admin/install.php'})

        def fake_render(request, template_name, context, status):
            return HttpResponse(status=status)

        with patch('djangoblog.error_views.render', side_effect=fake_render):
            with self.assertLogs('djangoblog.error_views', level='DEBUG') as logs:
                response = render_error_page(request, 404, 'Not found', exception)

        self.assertEqual(response.status_code, 404)
        self.assertIn('HTTP 404 for /wp-admin/install.php: Resolver404', logs.output[0])
        self.assertNotIn('Traceback', logs.output[0])
