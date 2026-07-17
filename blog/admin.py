from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

# Register your models here.
from .models import Article, BookmarkStat, Category, Tag, Links, NewsItem, SideBar, BlogSettings


class ArticleForm(forms.ModelForm):
    # body = forms.CharField(widget=AdminPagedownWidget())

    class Meta:
        model = Article
        fields = '__all__'


def makr_article_publish(modeladmin, request, queryset):
    queryset.update(status='p')


def draft_article(modeladmin, request, queryset):
    queryset.update(status='d')


def close_article_commentstatus(modeladmin, request, queryset):
    queryset.update(comment_status='c')


def open_article_commentstatus(modeladmin, request, queryset):
    queryset.update(comment_status='o')


makr_article_publish.short_description = _('Publish selected articles')
draft_article.short_description = _('Draft selected articles')
close_article_commentstatus.short_description = _('Close article comments')
open_article_commentstatus.short_description = _('Open article comments')


class ArticlelAdmin(admin.ModelAdmin):
    list_per_page = 20
    search_fields = ('body', 'title', 'body_en', 'title_en')
    form = ArticleForm
    list_display = (
        'id',
        'title',
        'title_en',
        'author',
        'link_to_category',
        'creation_time',
        'views',
        'status',
        'type',
        'has_english_version',
        'article_order')
    list_display_links = ('id', 'title')
    list_filter = ('status', 'type', 'category')
    date_hierarchy = 'creation_time'
    filter_horizontal = ('tags',)
    exclude = ('creation_time', 'last_modify_time')
    view_on_site = True
    actions = [
        makr_article_publish,
        draft_article,
        close_article_commentstatus,
        open_article_commentstatus]
    raw_id_fields = ('author', 'category',)

    fieldsets = (
        (None, {
            'fields': (
                'title',
                'body',
                'title_en',
                'body_en',
                'seo_description_en',
                'pub_time',
                'status',
                'comment_status',
                'type',
                'views',
                'author',
                'article_order',
                'show_toc',
                'category',
                'tags',
            )
        }),
    )

    def link_to_category(self, obj):
        info = (obj.category._meta.app_label, obj.category._meta.model_name)
        link = reverse('admin:%s_%s_change' % info, args=(obj.category.id,))
        return format_html(u'<a href="%s">%s</a>' % (link, obj.category.name))

    link_to_category.short_description = _('category')

    def has_english_version(self, obj):
        return obj.has_english_content()

    has_english_version.boolean = True
    has_english_version.short_description = _('English version')

    def get_form(self, request, obj=None, **kwargs):
        form = super(ArticlelAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['author'].queryset = get_user_model(
        ).objects.filter(is_superuser=True)
        return form

    def save_model(self, request, obj, form, change):
        super(ArticlelAdmin, self).save_model(request, obj, form, change)

    def get_view_on_site_url(self, obj=None):
        if obj:
            url = obj.get_full_url()
            return url
        else:
            from djangoblog.utils import get_current_site
            site = get_current_site().domain
            return site


class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'name_en')
    search_fields = ('name', 'name_en')
    exclude = ('slug', 'last_mod_time', 'creation_time')


class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'name_en', 'parent_category', 'index')
    search_fields = ('name', 'name_en')
    exclude = ('slug', 'last_mod_time', 'creation_time')


class LinksAdmin(admin.ModelAdmin):
    exclude = ('last_mod_time', 'creation_time')


class NewsItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'source', 'source_name', 'published_at', 'fetched_at', 'is_visible')
    list_filter = ('source', 'is_visible', 'published_at')
    search_fields = (
        'title', 'summary', 'content', 'reason', 'source_name',
        'source_url', 'original_url', 'tags',
    )
    readonly_fields = ('fetched_at',)


class SideBarAdmin(admin.ModelAdmin):
    list_display = ('name', 'content', 'is_enable', 'sequence')
    exclude = ('last_mod_time', 'creation_time')


class BlogSettingsAdmin(admin.ModelAdmin):
    """单例配置Admin - 直接跳转到编辑页面"""

    fieldsets = (
        (_('Site identity'), {
            'fields': (
                'site_name',
                'site_name_en',
                'site_description',
                'site_description_en',
                'site_seo_description',
                'site_seo_description_en',
                'site_keywords',
            )
        }),
        (_('Content display'), {
            'fields': (
                'article_sub_length',
                'sidebar_article_count',
                'sidebar_comment_count',
                'article_comment_count',
                'open_site_comment',
                'comment_need_review',
                'show_api_promo',
                'color_scheme',
            )
        }),
        (_('Integrations'), {
            'fields': (
                'show_google_adsense',
                'google_adsense_codes',
                'analytics_code',
                'beian_code',
                'show_gongan_code',
                'gongan_beiancode',
            )
        }),
        (_('Custom HTML'), {
            'fields': (
                'global_header',
                'global_footer',
            )
        }),
    )

    def has_add_permission(self, request):
        """如果已经存在配置，则禁止添加"""
        return not BlogSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """禁止删除配置"""
        return False

    def changelist_view(self, request, extra_context=None):
        """列表页直接跳转到编辑页面"""
        from django.http import HttpResponseRedirect
        obj = BlogSettings.objects.first()
        if obj:
            return HttpResponseRedirect(
                reverse('admin:blog_blogsettings_change', args=[obj.pk])
            )
        # 如果不存在配置，跳转到添加页面
        return HttpResponseRedirect(
            reverse('admin:blog_blogsettings_add')
        )

    def save_model(self, request, obj, form, change):
        """保存设置时清除缓存"""
        super().save_model(request, obj, form, change)
        # 确保缓存被清除
        from djangoblog.utils import cache
        cache.clear()
        self.message_user(request, '设置已保存，缓存已清除')


class BookmarkStatAdmin(admin.ModelAdmin):
    list_display = ('bookmark_count',)

    def has_add_permission(self, request):
        return not BookmarkStat.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
