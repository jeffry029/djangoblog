from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseNotFound

from blog.traffic import (
    get_client_ip,
    is_watched_public_route,
    record_public_visit,
    request_fingerprint,
    route_name_for_path,
)


class PublicReadOnlyMiddleware:
    """Expose only public browsing endpoints when the site runs in read-only mode."""

    blocked_prefixes = (
        '/admin/',
        '/login/',
        '/logout/',
        '/register/',
        '/forget_password/',
        '/forget_password_code/',
        '/account/',
        '/oauth/',
        '/mdeditor/',
        '/owntracks/',
        '/robot/',
    )
    blocked_exact_paths = (
        '/admin',
        '/login',
        '/logout',
        '/register',
        '/forget_password',
        '/forget_password_code',
        '/account',
        '/oauth',
        '/mdeditor',
        '/owntracks',
        '/robot',
        '/clean',
        '/upload',
    )
    allowed_methods = {'GET', 'HEAD'}
    allowed_internal_state_paths = (
        '/_internal/api-promo/',
        '/_internal/feedback/submit/',
    )
    rate_limit_window = 60
    rate_limit_max_requests = 180
    list_rate_limit_max_requests = 60
    fingerprint_rate_limit_max_requests = 90

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'PUBLIC_READ_ONLY_MODE', True):
            path = request.path_info
            if (
                request.method.upper() not in self.allowed_methods
                and path not in self.allowed_internal_state_paths
            ):
                return HttpResponseNotFound()
            if path in self.blocked_exact_paths or any(path.startswith(prefix) for prefix in self.blocked_prefixes):
                return HttpResponseNotFound()
            if self._is_rate_limited(request):
                return HttpResponse('Too Many Requests', status=429)
            if self._is_list_route_rate_limited(request):
                return HttpResponse('Too Many Requests', status=429)
            if self._is_fingerprint_rate_limited(request):
                return HttpResponse('Too Many Requests', status=429)
        response = self.get_response(request)
        if getattr(settings, 'PUBLIC_READ_ONLY_MODE', True) and response.status_code < 400:
            record_public_visit(request)
        return response

    def _is_rate_limited(self, request):
        max_requests = int(getattr(settings, 'PUBLIC_RATE_LIMIT_PER_MINUTE', self.rate_limit_max_requests))
        return self._hit_limit(f'public-read-only-rate:{self._client_ip(request)}', max_requests)

    def _is_list_route_rate_limited(self, request):
        if not is_watched_public_route(request):
            return False
        max_requests = int(getattr(
            settings,
            'PUBLIC_LIST_RATE_LIMIT_PER_MINUTE',
            self.list_rate_limit_max_requests,
        ))
        route_name = route_name_for_path(request.path_info)
        key = f'public-list-rate:{self._client_ip(request)}:{route_name}'
        return self._hit_limit(key, max_requests)

    def _is_fingerprint_rate_limited(self, request):
        if not is_watched_public_route(request):
            return False
        max_requests = int(getattr(
            settings,
            'PUBLIC_FINGERPRINT_RATE_LIMIT_PER_MINUTE',
            self.fingerprint_rate_limit_max_requests,
        ))
        key = f'public-fingerprint-rate:{self._client_ip(request)}:{request_fingerprint(request)}'
        return self._hit_limit(key, max_requests)

    def _hit_limit(self, key, max_requests):
        if max_requests <= 0:
            return False

        current = cache.get(key)
        if current is None:
            cache.set(key, 1, self.rate_limit_window)
            return False
        if current >= max_requests:
            return True
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, self.rate_limit_window)
        return False

    @staticmethod
    def _client_ip(request):
        return get_client_ip(request)
