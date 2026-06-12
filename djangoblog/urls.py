"""djangoblog URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.http import Http404
from django.urls import path, include
from django.urls import re_path
from django.http import HttpResponse, JsonResponse
import time
from pathlib import Path

from djangoblog.feeds import DjangoBlogFeed
from djangoblog.sitemap import ArticleSiteMap, CategorySiteMap, StaticViewSitemap, TagSiteMap, UserSiteMap
from blog.views import title_search_view

sitemaps = {

    'blog': ArticleSiteMap,
    'Category': CategorySiteMap,
    'Tag': TagSiteMap,
    'User': UserSiteMap,
    'static': StaticViewSitemap
}

handler404 = 'blog.views.page_not_found_view'
handler500 = 'blog.views.server_error_view'
handle403 = 'blog.views.permission_denied_view'


def health_check(request):
    """
    健康检查接口
    简单返回服务健康状态
    """
    return JsonResponse({
        'status': 'healthy',
        'timestamp': time.time()
    })


def robots_txt(request):
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /admin',
        'Disallow: /login',
        'Disallow: /oauth',
        'Disallow: /owntracks',
        'Disallow: /mdeditor',
        f'Sitemap: {request.scheme}://{request.get_host()}/sitemap.xml',
    ]
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain')


def indexnow_key_file(request, key):
    expected_key = getattr(settings, 'INDEXNOW_KEY', '')
    if key != expected_key:
        raise Http404

    key_path = Path(getattr(settings, 'INDEXNOW_KEY_FILE_PATH', ''))
    try:
        content = key_path.read_text(encoding='utf-8')
    except OSError:
        raise Http404
    return HttpResponse(content, content_type='text/plain')


urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    path('health/', health_check, name='health_check'),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps},
         name='django.contrib.sitemaps.views.sitemap'),
    re_path(r'^(?P<key>[0-9A-Za-z_-]{8,128})\.txt$', indexnow_key_file, name='indexnow_key_file'),
]
urlpatterns += i18n_patterns(
    re_path(r'', include('blog.urls', namespace='blog')),
    re_path(r'^feed/$', DjangoBlogFeed()),
    re_path(r'^rss/$', DjangoBlogFeed()),
    re_path('^search', title_search_view, name='search')
    , prefix_default_language=False) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
