import logging
import re
import hashlib
import random
from abc import abstractmethod
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.timezone import now
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from mdeditor.fields import MDTextField
from uuslug import slugify

from djangoblog.utils import cache_decorator, cache
from djangoblog.utils import get_current_site
from djangoblog.constants import CacheTimeout, CacheKey

logger = logging.getLogger(__name__)


def default_article_views():
    return random.randint(10, 30)


class LinkShowType(models.TextChoices):
    I = ('i', _('index'))
    L = ('l', _('list'))
    P = ('p', _('post'))
    A = ('a', _('all'))
    S = ('s', _('slide'))


class BaseModel(models.Model):
    id = models.AutoField(primary_key=True)
    creation_time = models.DateTimeField(_('creation time'), default=now)
    last_modify_time = models.DateTimeField(_('modify time'), default=now)

    def save(self, *args, **kwargs):
        is_update_views = isinstance(
            self,
            Article) and 'update_fields' in kwargs and kwargs['update_fields'] == ['views']
        if is_update_views:
            Article.objects.filter(pk=self.pk).update(views=self.views)
        else:
            if 'slug' in self.__dict__:
                slug = getattr(
                    self, 'title') if 'title' in self.__dict__ else getattr(
                    self, 'name')
                setattr(self, 'slug', slugify(slug))
            super().save(*args, **kwargs)

    def get_full_url(self):
        site = get_current_site().domain
        url = "https://{site}{path}".format(site=site,
                                            path=self.get_absolute_url())
        return url

    class Meta:
        abstract = True

    @abstractmethod
    def get_absolute_url(self):
        pass


class Article(BaseModel):
    """文章"""
    STATUS_CHOICES = (
        ('d', _('Draft')),
        ('p', _('Published')),
    )
    COMMENT_STATUS = (
        ('o', _('Open')),
        ('c', _('Close')),
    )
    TYPE = (
        ('a', _('Article')),
        ('p', _('Page')),
    )
    title = models.CharField(_('title'), max_length=200, unique=True)
    body = MDTextField(_('body'))
    title_en = models.CharField(_('English title'), max_length=200, blank=True, default='')
    body_en = MDTextField(_('English body'), blank=True, default='')
    seo_description_en = models.TextField(_('English SEO description'), blank=True, default='')
    pub_time = models.DateTimeField(
        _('publish time'), blank=False, null=False, default=now)
    status = models.CharField(
        _('status'),
        max_length=1,
        choices=STATUS_CHOICES,
        default='p')
    comment_status = models.CharField(
        _('comment status'),
        max_length=1,
        choices=COMMENT_STATUS,
        default='o')
    type = models.CharField(_('type'), max_length=1, choices=TYPE, default='a')
    views = models.PositiveIntegerField(_('views'), default=default_article_views)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('author'),
        blank=False,
        null=False,
        on_delete=models.CASCADE)
    article_order = models.IntegerField(
        _('order'), blank=False, null=False, default=0)
    show_toc = models.BooleanField(_('show toc'), blank=False, null=False, default=False)
    category = models.ForeignKey(
        'Category',
        verbose_name=_('category'),
        on_delete=models.CASCADE,
        blank=False,
        null=False)
    tags = models.ManyToManyField('Tag', verbose_name=_('tag'), blank=True)

    def body_to_string(self):
        return self.get_body()

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-article_order', '-pub_time']
        verbose_name = _('article')
        verbose_name_plural = verbose_name
        get_latest_by = 'id'
        indexes = [
            # 优化列表查询：type + status + pub_time组合索引
            models.Index(fields=['type', 'status', '-pub_time'], name='idx_type_status_pub'),
            # 优化热门文章查询：status + views组合索引
            models.Index(fields=['status', '-views'], name='idx_status_views'),
            # 优化作者文章查询：author + status + type组合索引
            models.Index(fields=['author', 'status', 'type'], name='idx_author_status_type'),
            # 优化分类查询：category + status组合索引
            models.Index(fields=['category', 'status'], name='idx_category_status'),
        ]

    def get_absolute_url(self):
        return reverse('blog:detailbyid', kwargs={
            'article_id': self.id,
            'year': self.creation_time.year,
            'month': self.creation_time.month,
            'day': self.creation_time.day
        })

    def get_absolute_url_for_language(self, language_code):
        with translation.override(language_code):
            return self.get_absolute_url()

    def get_full_url_for_language(self, language_code):
        site = get_current_site().domain
        return "https://{site}{path}".format(
            site=site,
            path=self.get_absolute_url_for_language(language_code),
        )

    @staticmethod
    def _is_english_language(language_code=None):
        language_code = language_code or translation.get_language() or settings.LANGUAGE_CODE
        return language_code.lower().startswith('en')

    @staticmethod
    def _clean_localized_value(value):
        return (value or '').strip()

    def has_english_content(self):
        return bool(self._clean_localized_value(self.title_en) and self._clean_localized_value(self.body_en))

    def get_title(self, language_code=None):
        if self._is_english_language(language_code):
            title = self._clean_localized_value(self.title_en)
            if title:
                return title
        return self.title

    def get_body(self, language_code=None):
        if self._is_english_language(language_code):
            body = self._clean_localized_value(self.body_en)
            if body:
                return body
        return self.body

    def get_seo_description(self, language_code=None):
        if self._is_english_language(language_code):
            description = self._clean_localized_value(self.seo_description_en)
            if description:
                return description
        return ''

    @cache_decorator(CacheTimeout.HOUR_10)
    def get_category_tree(self, language_code=None):
        tree = self.category.get_category_tree()
        names = list(map(lambda c: (c.get_name(language_code), c.get_absolute_url()), tree))

        return names

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def viewed(self):
        self.views += 1
        self.save(update_fields=['views'])

    def comment_list(self):
        cache_key = CacheKey.ARTICLE_COMMENTS.format(article_id=self.id)
        value = cache.get(cache_key)
        if value:
            logger.info(f'Cache HIT: article comments (id={self.id})')
            return value
        else:
            comments = self.comment_set.filter(is_enable=True).order_by('-id')
            cache.set(cache_key, comments, CacheTimeout.HOUR_10)
            logger.info(f'Cache MISS: article comments (id={self.id})')
            return comments

    def get_admin_url(self):
        info = (self._meta.app_label, self._meta.model_name)
        return reverse('admin:%s_%s_change' % info, args=(self.pk,))

    @cache_decorator(expiration=CacheTimeout.HOUR_10)
    def next_article(self):
        # 下一篇
        return Article.objects.filter(
            id__gt=self.id, status='p').order_by('id').first()

    @cache_decorator(expiration=CacheTimeout.HOUR_10)
    def prev_article(self):
        # 前一篇
        return Article.objects.filter(id__lt=self.id, status='p').first()

    def get_first_image_url(self):
        """
        Get the first image url from article.body.
        :return:
        """
        match = re.search(r'!\[.*?\]\((.+?)\)', self.get_body())
        if match:
            return match.group(1)
        return ""


class Category(BaseModel):
    """文章分类"""
    name = models.CharField(_('category name'), max_length=30, unique=True)
    name_en = models.CharField(_('English category name'), max_length=60, blank=True, default='')
    parent_category = models.ForeignKey(
        'self',
        verbose_name=_('parent category'),
        blank=True,
        null=True,
        on_delete=models.CASCADE)
    slug = models.SlugField(default='no-slug', max_length=60, blank=True)
    index = models.IntegerField(default=0, verbose_name=_('index'))

    class Meta:
        ordering = ['-index']
        verbose_name = _('category')
        verbose_name_plural = verbose_name

    def get_absolute_url(self):
        return reverse(
            'blog:category_detail', kwargs={
                'category_name': self.slug})

    def __str__(self):
        return self.name

    @staticmethod
    def _is_english_language(language_code=None):
        language_code = language_code or translation.get_language() or settings.LANGUAGE_CODE
        return language_code.lower().startswith('en')

    @staticmethod
    def _clean_localized_value(value):
        return (value or '').strip()

    def get_name(self, language_code=None):
        if self._is_english_language(language_code):
            name = self._clean_localized_value(self.name_en)
            if name:
                return name
        return self.name

    @cache_decorator(CacheTimeout.HOUR_10)
    def get_category_tree(self):
        """
        递归获得分类目录的父级
        :return:
        """
        categorys = []

        def parse(category):
            categorys.append(category)
            if category.parent_category:
                parse(category.parent_category)

        parse(self)
        return categorys

    @cache_decorator(CacheTimeout.HOUR_10)
    def get_sub_categorys(self):
        """
        获得当前分类目录所有子集
        :return:
        """
        categorys = []
        all_categorys = Category.objects.all()

        def parse(category):
            if category not in categorys:
                categorys.append(category)
            childs = all_categorys.filter(parent_category=category)
            for child in childs:
                if category not in categorys:
                    categorys.append(child)
                parse(child)

        parse(self)
        return categorys


class Tag(BaseModel):
    """文章标签"""
    name = models.CharField(_('tag name'), max_length=30, unique=True)
    name_en = models.CharField(_('English tag name'), max_length=60, blank=True, default='')
    slug = models.SlugField(default='no-slug', max_length=60, blank=True)

    def __str__(self):
        return self.name

    def get_name(self, language_code=None):
        language_code = language_code or translation.get_language() or settings.LANGUAGE_CODE
        if language_code.lower().startswith('en'):
            name = (self.name_en or '').strip()
            if name:
                return name
        return self.name

    def get_absolute_url(self):
        return reverse('blog:tag_detail', kwargs={'tag_name': self.slug})

    @cache_decorator(CacheTimeout.HOUR_10)
    def get_article_count(self):
        return Article.objects.filter(tags__name=self.name).distinct().count()

    class Meta:
        ordering = ['name']
        verbose_name = _('tag')
        verbose_name_plural = verbose_name


class Links(models.Model):
    """友情链接"""

    name = models.CharField(_('link name'), max_length=30, unique=True)
    link = models.URLField(_('link'))
    sequence = models.IntegerField(_('order'), unique=True)
    is_enable = models.BooleanField(
        _('is show'), default=True, blank=False, null=False)
    show_type = models.CharField(
        _('show type'),
        max_length=1,
        choices=LinkShowType.choices,
        default=LinkShowType.I)
    creation_time = models.DateTimeField(_('creation time'), default=now)
    last_mod_time = models.DateTimeField(_('modify time'), default=now)

    class Meta:
        ordering = ['sequence']
        verbose_name = _('link')
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class NewsItem(models.Model):
    """抓取到的技术新闻。"""

    SOURCE_CHOICES = (
        ('aihot', 'AI HOT'),
        ('tech', '技术站点'),
    )

    title = models.CharField('标题', max_length=300)
    summary = models.TextField('摘要', blank=True, default='')
    content = models.TextField('正文', blank=True, default='')
    reason = models.TextField('推荐理由', blank=True, default='')
    source = models.CharField('来源', max_length=50, choices=SOURCE_CHOICES, default='aihot')
    source_name = models.CharField('来源名称', max_length=120, blank=True, default='')
    source_url = models.URLField('采集来源链接', max_length=1000)
    source_url_hash = models.CharField('采集来源链接哈希', max_length=64, unique=True, blank=True, default='')
    original_url = models.URLField('原文链接', max_length=1000, blank=True, default='')
    tags = models.CharField('标签', max_length=300, blank=True, default='')
    published_at = models.DateTimeField('发布时间', null=True, blank=True)
    fetched_at = models.DateTimeField('抓取时间', default=now)
    is_visible = models.BooleanField('是否展示', default=True)

    class Meta:
        ordering = ['-published_at', '-fetched_at']
        verbose_name = '新闻'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['source', '-published_at'], name='idx_news_source_pub'),
            models.Index(fields=['is_visible', '-fetched_at'], name='idx_news_visible_fetch'),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('blog:news_detail', kwargs={'news_id': self.id})

    def has_detail_content(self):
        return bool(strip_tags(self.content or '').strip())

    def get_display_url(self):
        return self.get_absolute_url() if self.has_detail_content() else self.source_url

    def get_aihot_url(self):
        try:
            hostname = (urlparse(self.source_url).hostname or '').lower()
        except ValueError:
            return ''
        return self.source_url if hostname == 'aihot.virxact.com' else ''

    def get_original_url(self):
        return self.original_url or ('' if self.get_aihot_url() else self.source_url)

    def save(self, *args, **kwargs):
        self.source_url_hash = hashlib.sha256(self.source_url.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)


class PublicTrafficDailyStat(models.Model):
    """Aggregated public browser traffic for operational visibility."""

    date = models.DateField('日期', db_index=True)
    route_name = models.CharField('路由', max_length=40)
    path = models.CharField('路径', max_length=255)
    ip_address = models.GenericIPAddressField('IP 地址', unpack_ipv4=True)
    fingerprint = models.CharField('请求指纹', max_length=64)
    user_agent = models.CharField('User-Agent', max_length=500, blank=True, default='')
    visit_count = models.PositiveIntegerField('访问次数', default=0)
    first_seen = models.DateTimeField('首次访问', default=now)
    last_seen = models.DateTimeField('最近访问', default=now)

    class Meta:
        verbose_name = '公开访问统计'
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=['date', 'route_name', 'path', 'ip_address', 'fingerprint'],
                name='uniq_public_traffic_daily_identity',
            ),
        ]
        indexes = [
            models.Index(fields=['date', 'route_name'], name='idx_traffic_date_route'),
            models.Index(fields=['date', 'path'], name='idx_traffic_date_path'),
        ]

    def __str__(self):
        return f'{self.date} {self.route_name} {self.ip_address} {self.visit_count}'


class BookmarkStat(models.Model):
    """Singleton model tracking total bookmark count."""
    bookmark_count = models.PositiveIntegerField(_('bookmark count'), default=0)

    class Meta:
        verbose_name = _('bookmark stat')
        verbose_name_plural = verbose_name

    @classmethod
    def get_singleton(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return str(self.bookmark_count)


class SideBar(models.Model):
    """侧边栏,可以展示一些html内容"""
    name = models.CharField(_('title'), max_length=100)
    content = models.TextField(_('content'))
    sequence = models.IntegerField(_('order'), unique=True)
    is_enable = models.BooleanField(_('is enable'), default=True)
    creation_time = models.DateTimeField(_('creation time'), default=now)
    last_mod_time = models.DateTimeField(_('modify time'), default=now)

    class Meta:
        ordering = ['sequence']
        verbose_name = _('sidebar')
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class BlogSettings(models.Model):
    """blog的配置"""

    COLOR_SCHEMES = (
        ('purple', _('紫色主题 - Purple Dream')),
        ('blue', _('蓝色主题 - Ocean Blue')),
        ('green', _('绿色主题 - Forest Green')),
        ('orange', _('橙色主题 - Sunset Orange')),
        ('pink', _('粉色主题 - Cherry Blossom')),
        ('red', _('红色主题 - Ruby Red')),
        ('indigo', _('靛蓝主题 - Midnight Indigo')),
        ('teal', _('青色主题 - Teal Wave')),
    )

    site_name = models.CharField(
        _('site name'),
        max_length=200,
        null=False,
        blank=False,
        default='')
    site_name_en = models.CharField(
        _('English site name'),
        max_length=200,
        blank=True,
        default='')
    site_description = models.TextField(
        _('site description'),
        max_length=1000,
        null=False,
        blank=False,
        default='')
    site_description_en = models.TextField(
        _('English site description'),
        max_length=1000,
        blank=True,
        default='')
    site_seo_description = models.TextField(
        _('site seo description'), max_length=1000, null=False, blank=False, default='')
    site_seo_description_en = models.TextField(
        _('English site SEO description'), max_length=1000, blank=True, default='')
    site_keywords = models.TextField(
        _('site keywords'),
        max_length=1000,
        null=False,
        blank=False,
        default='')
    article_sub_length = models.IntegerField(_('article sub length'), default=300)
    sidebar_article_count = models.IntegerField(_('sidebar article count'), default=10)
    sidebar_comment_count = models.IntegerField(_('sidebar comment count'), default=5)
    article_comment_count = models.IntegerField(_('article comment count'), default=5)
    show_google_adsense = models.BooleanField(_('show adsense'), default=False)
    google_adsense_codes = models.TextField(
        _('adsense code'), max_length=2000, null=True, blank=True, default='')
    show_api_promo = models.BooleanField('是否显示 API 中转推广', default=False)
    open_site_comment = models.BooleanField(_('open site comment'), default=True)
    color_scheme = models.CharField(
        _('配色方案'),
        max_length=20,
        choices=COLOR_SCHEMES,
        default='purple',
        help_text=_('选择网站的主题配色方案'))
    global_header = models.TextField("公共头部", null=True, blank=True, default='')
    global_footer = models.TextField("公共尾部", null=True, blank=True, default='')
    beian_code = models.CharField(
        '备案号',
        max_length=2000,
        null=True,
        blank=True,
        default='')
    analytics_code = models.TextField(
        "网站统计代码",
        max_length=1000,
        null=False,
        blank=False,
        default='')
    show_gongan_code = models.BooleanField(
        '是否显示公安备案号', default=False, null=False)
    gongan_beiancode = models.TextField(
        '公安备案号',
        max_length=2000,
        null=True,
        blank=True,
        default='')
    comment_need_review = models.BooleanField(
        '评论是否需要审核', default=False, null=False)

    class Meta:
        verbose_name = _('Website configuration')
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.site_name

    @staticmethod
    def _is_english_language(language_code=None):
        language_code = language_code or translation.get_language() or settings.LANGUAGE_CODE
        return language_code.lower().startswith('en')

    @staticmethod
    def _clean_localized_value(value):
        return (value or '').strip()

    def get_site_name(self, language_code=None):
        if self._is_english_language(language_code):
            site_name = self._clean_localized_value(self.site_name_en)
            if site_name:
                return site_name
        return self.site_name

    def get_site_description(self, language_code=None):
        if self._is_english_language(language_code):
            description = self._clean_localized_value(self.site_description_en)
            if description:
                return description
        return self.site_description

    def get_site_seo_description(self, language_code=None):
        if self._is_english_language(language_code):
            description = self._clean_localized_value(self.site_seo_description_en)
            if description:
                return description
        return self.site_seo_description

    def clean(self):
        if BlogSettings.objects.exclude(id=self.id).count():
            raise ValidationError(_('There can only be one configuration'))

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from djangoblog.utils import cache
        cache.clear()


class Feedback(models.Model):
    """用户建议反馈"""

    content = models.TextField('反馈内容')
    contact = models.CharField('联系方式', max_length=200, blank=True, default='')
    ip_address = models.GenericIPAddressField('IP 地址', unpack_ipv4=True)
    user_agent = models.CharField('User-Agent', max_length=500, blank=True, default='')
    referer = models.CharField('来源页面', max_length=500, blank=True, default='')
    idempotency_key = models.CharField('幂等键', max_length=64, unique=True)
    created_at = models.DateTimeField('提交时间', default=now)

    class Meta:
        verbose_name = '用户反馈'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at'], name='idx_feedback_created'),
            models.Index(fields=['ip_address', '-created_at'], name='idx_feedback_ip_time'),
        ]

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} {self.ip_address} - {self.content[:30]}'
