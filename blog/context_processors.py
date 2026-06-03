import logging

from django.conf import settings
from django.utils import timezone

from djangoblog.utils import cache, get_blog_setting
from .models import Category, Article

logger = logging.getLogger(__name__)
PUBLIC_SITE_NAME = '开发者雷达'
PUBLIC_SITE_DESCRIPTION = 'AI 精选与摘要技术文章、编程实践和人工智能新闻。'


def seo_processor(requests):
    key = 'seo_processor'
    value = cache.get(key)
    if value:
        # 更新动态值（不需要缓存的内容）
        value['SITE_BASE_URL'] = requests.scheme + '://' + requests.get_host() + '/'
        value['CURRENT_YEAR'] = timezone.now().year
        value['SITE_NAME'] = PUBLIC_SITE_NAME
        value['SITE_DESCRIPTION'] = PUBLIC_SITE_DESCRIPTION
        value['SITE_SEO_DESCRIPTION'] = PUBLIC_SITE_DESCRIPTION
        value['SHOW_API_PROMO'] = settings.SHOW_API_PROMO
        return value
    else:
        logger.info('set processor cache.')
        setting = get_blog_setting()

        # 优化查询：预加载关联数据
        nav_category_list = Category.objects.all()
        nav_pages = Article.objects.filter(
            type='p',
            status='p'
        )

        value = {
            'SITE_NAME': PUBLIC_SITE_NAME,
            'SHOW_GOOGLE_ADSENSE': setting.show_google_adsense,
            'GOOGLE_ADSENSE_CODES': setting.google_adsense_codes,
            'SHOW_API_PROMO': settings.SHOW_API_PROMO,
            'SITE_SEO_DESCRIPTION': PUBLIC_SITE_DESCRIPTION,
            'SITE_DESCRIPTION': PUBLIC_SITE_DESCRIPTION,
            'SITE_KEYWORDS': setting.site_keywords,
            'SITE_BASE_URL': requests.scheme + '://' + requests.get_host() + '/',
            'ARTICLE_SUB_LENGTH': setting.article_sub_length,
            'nav_category_list': nav_category_list,  # 保持QuerySet
            'nav_pages': nav_pages,  # 保持QuerySet
            'OPEN_SITE_COMMENT': setting.open_site_comment,
            'BEIAN_CODE': setting.beian_code,
            'ANALYTICS_CODE': setting.analytics_code,
            "BEIAN_CODE_GONGAN": setting.gongan_beiancode,
            "SHOW_GONGAN_CODE": setting.show_gongan_code,
            "CURRENT_YEAR": timezone.now().year,
            "GLOBAL_HEADER": setting.global_header,
            "GLOBAL_FOOTER": setting.global_footer,
            "COMMENT_NEED_REVIEW": setting.comment_need_review,
            "COLOR_SCHEME": setting.color_scheme,
        }
        cache.set(key, value, 60 * 60 * 10)
        return value
