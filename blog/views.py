import logging
import os
import re
import uuid

from blog.context_processors import PUBLIC_SITE_NAME
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import F, Sum
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.templatetags.static import static
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from haystack.views import SearchView

from blog.models import Article, BookmarkStat, BlogSettings, Category, Feedback, LinkShowType, Links, NewsItem, PublicTrafficDailyStat, Tag
from djangoblog.plugin_manage import hooks
from djangoblog.plugin_manage.hook_constants import ARTICLE_CONTENT_HOOK_NAME
from djangoblog.utils import cache, get_blog_setting, get_sha256
from djangoblog.mixins import (
    SlugCachedMixin,
    ArticleListMixin,
    OptimizedArticleQueryMixin,
    CachedListViewMixin,
    PageNumberMixin
)

logger = logging.getLogger(__name__)


class ArticleListView(CachedListViewMixin, PageNumberMixin, ListView):
    """
    文章列表视图基类（重构版）

    使用 Mixin 简化代码，消除重复逻辑
    子类只需实现 get_queryset_data() 和 get_queryset_cache_key() 方法
    """
    # template_name属性用于指定使用哪个模板进行渲染
    template_name = 'blog/article_index.html'

    # context_object_name属性用于给上下文变量取名（在模板中使用该名字）
    context_object_name = 'article_list'

    # 页面类型，分类目录或标签列表等
    page_type = ''
    paginate_by = settings.PAGINATE_BY
    page_kwarg = 'page'
    link_type = LinkShowType.L

    def get_view_cache_key(self):
        return self.request.get['pages']

    def get_context_data(self, **kwargs):
        kwargs['linktype'] = self.link_type
        return super(ArticleListView, self).get_context_data(**kwargs)


class IndexView(OptimizedArticleQueryMixin, ArticleListView):
    """
    首页视图（重构版）

    继承 OptimizedArticleQueryMixin 获得优化的查询方法
    """
    # 友情链接类型
    link_type = LinkShowType.I

    def get_queryset_data(self):
        # 使用 Mixin 提供的优化查询方法
        return self.get_optimized_article_queryset().filter(
            type='a', status='p'
        )

    def get_queryset_cache_key(self):
        return f'index_{self.page_number}'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        blog_setting = get_blog_setting()
        # 提供基础SEO数据
        context['seo_title'] = "开发者雷达"
        context['seo_description'] = "AI 精选与摘要技术文章、编程实践和人工智能新闻。"
        context['seo_keywords'] = blog_setting.site_keywords
        return context


class NewsListView(ListView):
    """新闻列表页面。"""

    template_name = 'blog/news_list.html'
    context_object_name = 'news_list'
    paginate_by = 20

    def get_queryset(self):
        return NewsItem.objects.filter(is_visible=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        blog_setting = get_blog_setting()
        context['seo_title'] = f"AI 快讯 | {PUBLIC_SITE_NAME}"
        context['seo_description'] = "AI 与技术新闻快讯。"
        context['seo_keywords'] = f"技术新闻,AI新闻,{blog_setting.site_keywords}"
        context['linktype'] = LinkShowType.L
        return context


def public_traffic_stats_view(request):
    configured_token = getattr(settings, 'PUBLIC_TRAFFIC_STATS_TOKEN', '')
    supplied_token = request.GET.get('token') or request.headers.get('X-Traffic-Stats-Token')
    if not configured_token or supplied_token != configured_token:
        raise Http404()

    stats = PublicTrafficDailyStat.objects.all()
    exact_date = parse_date(request.GET.get('date') or '')
    start_date = parse_date(request.GET.get('start') or '')
    end_date = parse_date(request.GET.get('end') or '')

    if exact_date:
        stats = stats.filter(date=exact_date)
    else:
        if start_date:
            stats = stats.filter(date__gte=start_date)
        if end_date:
            stats = stats.filter(date__lte=end_date)

    try:
        limit = int(request.GET.get('limit', '100'))
    except ValueError:
        limit = 100
    limit = max(1, min(limit, 1000))

    rows = list(stats.order_by('-date', '-visit_count', '-last_seen')[:limit])
    total = stats.aggregate(total=Sum('visit_count'))['total'] or 0
    return JsonResponse({
        'total_visits': total,
        'rows': [
            {
                'date': row.date.isoformat(),
                'route_name': row.route_name,
                'path': row.path,
                'ip_address': row.ip_address,
                'fingerprint': row.fingerprint,
                'user_agent': row.user_agent,
                'visit_count': row.visit_count,
                'first_seen': row.first_seen.isoformat(),
                'last_seen': row.last_seen.isoformat(),
            }
            for row in rows
        ],
    })


@csrf_exempt
def api_promo_control_view(request):
    configured_token = getattr(settings, 'API_PROMO_CONTROL_TOKEN', '')
    supplied_token = request.GET.get('token') or request.POST.get('token') or request.headers.get('X-Api-Promo-Token')
    if not configured_token or supplied_token != configured_token:
        raise Http404()

    blog_setting = get_blog_setting()
    if request.method == 'POST':
        enabled = (request.POST.get('enabled') or '').strip().lower()
        if enabled not in ('true', 'false', '1', '0', 'yes', 'no', 'on', 'off'):
            return JsonResponse({
                'error': 'enabled must be true or false',
                'enabled': blog_setting.show_api_promo,
            }, status=400)

        blog_setting.show_api_promo = enabled in ('true', '1', 'yes', 'on')
        blog_setting.save(update_fields=['show_api_promo'])
        blog_setting = BlogSettings.objects.get(pk=blog_setting.pk)

    return JsonResponse({'enabled': blog_setting.show_api_promo})


def title_search_view(request):
    query = (request.GET.get('q') or '').strip()
    article_results = Article.objects.none()
    news_results = NewsItem.objects.none()

    if query:
        article_results = Article.objects.filter(
            title__icontains=query,
            type='a',
            status='p',
        ).select_related('category', 'author').prefetch_related('tags')[:30]
        news_results = NewsItem.objects.filter(
            title__icontains=query,
            is_visible=True,
        )[:30]

    return render(request, 'search/search.html', {
        'query': query,
        'article_results': article_results,
        'news_results': news_results,
        'result_count': len(article_results) + len(news_results),
    })


class ArticleDetailView(DetailView):
    '''
    文章详情页面
    '''
    template_name = 'blog/article_detail.html'
    model = Article
    pk_url_kwarg = 'article_id'
    context_object_name = "article"

    def get_context_data(self, **kwargs):
        # 优化：直接查询父评论，减少数据库查询
        from comments.models import Comment
        parent_comments = Comment.objects.filter(
            article=self.object,
            parent_comment=None,
            is_enable=True
        ).select_related('author').prefetch_related(
            'comment_set__author'  # 预加载子评论及其作者
        ).order_by('-id')

        # 获取所有评论用于总数显示
        article_comments = self.object.comment_list()

        blog_setting = get_blog_setting()
        paginator = Paginator(parent_comments, blog_setting.article_comment_count)
        page = self.request.GET.get('comment_page', '1')
        if not page.isnumeric():
            page = 1
        else:
            page = int(page)
            if page < 1:
                page = 1
            if page > paginator.num_pages:
                page = paginator.num_pages

        p_comments = paginator.page(page)
        next_page = p_comments.next_page_number() if p_comments.has_next() else None
        prev_page = p_comments.previous_page_number() if p_comments.has_previous() else None

        if next_page:
            kwargs[
                'comment_next_page_url'] = self.object.get_absolute_url() + f'?comment_page={next_page}#commentlist-container'
        if prev_page:
            kwargs[
                'comment_prev_page_url'] = self.object.get_absolute_url() + f'?comment_page={prev_page}#commentlist-container'
        kwargs['article_comments'] = article_comments
        kwargs['p_comments'] = p_comments
        kwargs['comment_count'] = len(
            article_comments) if article_comments else 0

        kwargs['next_article'] = self.object.next_article
        kwargs['prev_article'] = self.object.prev_article

        context = super(ArticleDetailView, self).get_context_data(**kwargs)
        article = self.object
        
        # 添加基础SEO数据
        blog_setting = get_blog_setting()
        from django.utils.html import strip_tags
        from django.utils.text import Truncator
        from djangoblog.utils import CommonMarkdown
        
        # 处理description：markdown -> HTML -> 纯文本，彻底去除格式
        html_content = CommonMarkdown.get_markdown(article.body)
        description = strip_tags(html_content)
        description = ' '.join(description.split())  # 规范化空白字符
        description = Truncator(description).chars(150, truncate='...')
        
        # 处理keywords：去除空格，用逗号分隔
        tags = [tag.name.strip() for tag in article.tags.all()]
        keywords = ", ".join(tags) if tags else blog_setting.site_keywords
        
        context['seo_title'] = f"{article.title} | {blog_setting.site_name}"
        context['seo_description'] = description
        context['seo_keywords'] = keywords
        
        # 触发文章详情加载钩子，让插件可以添加额外的上下文数据
        from djangoblog.plugin_manage.hook_constants import ARTICLE_DETAIL_LOAD
        hooks.run_action(ARTICLE_DETAIL_LOAD, article=article, context=context, request=self.request)
        
        # Action Hook, 通知插件"文章详情已获取"
        hooks.run_action('after_article_body_get', article=article, request=self.request)
        return context


class CategoryDetailView(SlugCachedMixin, OptimizedArticleQueryMixin, ArticleListView):
    """
    分类目录列表（重构版）

    使用 SlugCachedMixin 避免重复查询 Category
    使用 OptimizedArticleQueryMixin 优化文章查询
    """
    page_type = "分类目录归档"
    slug_url_kwarg = 'category_name'
    slug_model = Category

    def get_queryset_data(self):
        # 使用 Mixin 缓存的对象，只查询一次
        category = self.get_slug_object()
        categorynames = [c.name for c in category.get_sub_categorys()]

        return self.get_optimized_article_queryset().filter(
            category__name__in=categorynames, status='p'
        )

    def get_queryset_cache_key(self):
        # 复用缓存的对象，不再重复查询数据库
        category = self.get_slug_object()
        return f'category_list_{category.name}_{self.page_number}'

    def get_context_data(self, **kwargs):
        category = self.get_slug_object()
        categoryname = category.name

        try:
            categoryname = categoryname.split('/')[-1]
        except BaseException:
            pass

        kwargs['page_type'] = CategoryDetailView.page_type
        kwargs['tag_name'] = categoryname
        
        # 添加基础SEO数据
        blog_setting = get_blog_setting()
        article_count = self.get_queryset().count()
        kwargs['seo_title'] = f"{categoryname} | {blog_setting.site_name}"
        kwargs['seo_description'] = f"浏览 {categoryname} 分类下的所有文章，共 {article_count} 篇文章。"
        kwargs['seo_keywords'] = f"{categoryname}, {blog_setting.site_keywords}"
        
        return super(CategoryDetailView, self).get_context_data(**kwargs)


class AuthorDetailView(OptimizedArticleQueryMixin, ArticleListView):
    """
    作者详情页（重构版）

    使用 OptimizedArticleQueryMixin 优化文章查询
    """
    page_type = '作者文章归档'

    def get_queryset_cache_key(self):
        from uuslug import slugify
        author_name = slugify(self.kwargs['author_name'])
        return f'author_{author_name}_{self.page_number}'

    def get_queryset_data(self):
        author_name = self.kwargs['author_name']
        return self.get_optimized_article_queryset().filter(
            author__username=author_name, type='a', status='p'
        )

    def get_context_data(self, **kwargs):
        author_name = self.kwargs['author_name']
        kwargs['page_type'] = AuthorDetailView.page_type
        kwargs['tag_name'] = author_name
        
        # 添加基础SEO数据
        blog_setting = get_blog_setting()
        article_count = self.get_queryset().count()
        kwargs['seo_title'] = f"{author_name} 的文章 | {blog_setting.site_name}"
        kwargs['seo_description'] = f"浏览 {author_name} 发表的所有文章，共 {article_count} 篇。"
        kwargs['seo_keywords'] = f"{author_name}, {blog_setting.site_keywords}"
        
        return super(AuthorDetailView, self).get_context_data(**kwargs)


class TagDetailView(SlugCachedMixin, OptimizedArticleQueryMixin, ArticleListView):
    """
    标签列表页面（重构版）

    使用 SlugCachedMixin 避免重复查询 Tag
    使用 OptimizedArticleQueryMixin 优化文章查询
    """
    page_type = '分类标签归档'
    slug_url_kwarg = 'tag_name'
    slug_model = Tag

    def get_queryset_data(self):
        # 使用 Mixin 缓存的对象，只查询一次
        tag = self.get_slug_object()
        return self.get_optimized_article_queryset().filter(
            tags__name=tag.name, type='a', status='p'
        )

    def get_queryset_cache_key(self):
        # 复用缓存的对象，不再重复查询数据库
        tag = self.get_slug_object()
        return f'tag_{tag.name}_{self.page_number}'

    def get_context_data(self, **kwargs):
        tag = self.get_slug_object()
        kwargs['page_type'] = TagDetailView.page_type
        kwargs['tag_name'] = tag.name
        
        # 添加基础SEO数据
        blog_setting = get_blog_setting()
        article_count = self.get_queryset().count()
        kwargs['seo_title'] = f"{tag.name} | {blog_setting.site_name}"
        kwargs['seo_description'] = f"浏览所有关于 {tag.name} 的文章，共 {article_count} 篇内容。"
        kwargs['seo_keywords'] = f"{tag.name}, {blog_setting.site_keywords}"
        
        return super(TagDetailView, self).get_context_data(**kwargs)


class ArchivesView(OptimizedArticleQueryMixin, ArticleListView):
    """
    文章归档页面（重构版）

    使用 OptimizedArticleQueryMixin 优化文章查询
    """
    page_type = '文章归档'
    paginate_by = None
    page_kwarg = None
    template_name = 'blog/article_archives.html'

    def get_queryset_data(self):
        return self.get_optimized_article_queryset().filter(status='p')

    def get_queryset_cache_key(self):
        return 'archives'


class LinkListView(ListView):
    model = Links
    template_name = 'blog/links_list.html'

    def get_queryset(self):
        return Links.objects.filter(is_enable=True)


class EsSearchView(SearchView):
    def build_form(self, form_kwargs=None):
        """Override to enable highlighting"""
        if form_kwargs is None:
            form_kwargs = {}

        # Enable highlighting for search results
        from haystack.query import SearchQuerySet
        if self.searchqueryset is None:
            sqs = SearchQuerySet().highlight()
        else:
            sqs = self.searchqueryset.highlight()

        form_kwargs['searchqueryset'] = sqs
        return super().build_form(form_kwargs=form_kwargs)

    def get_context(self):
        paginator, page = self.build_page()
        context = {
            "query": self.query,
            "form": self.form,
            "page": page,
            "paginator": paginator,
            "suggestion": None,
        }
        if hasattr(self.results, "query") and self.results.query.backend.include_spelling:
            context["suggestion"] = self.results.query.get_spelling_suggestion()
        context.update(self.extra_context())

        return context


@csrf_exempt
def fileupload(request):
    """
    该方法需自己写调用端来上传图片，该方法仅提供图床功能
    :param request:
    :return:
    """
    if request.method == 'POST':
        sign = request.GET.get('sign', None)
        if not sign:
            return HttpResponseForbidden()
        if not sign == get_sha256(get_sha256(settings.SECRET_KEY)):
            return HttpResponseForbidden()
        response = []
        for filename in request.FILES:
            timestr = timezone.now().strftime('%Y/%m/%d')
            imgextensions = ['jpg', 'png', 'jpeg', 'bmp']
            fname = u''.join(str(filename))
            isimage = len([i for i in imgextensions if fname.find(i) >= 0]) > 0
            base_dir = os.path.join(settings.STATICFILES, "files" if not isimage else "image", timestr)
            if not os.path.exists(base_dir):
                os.makedirs(base_dir)
            savepath = os.path.normpath(os.path.join(base_dir, f"{uuid.uuid4().hex}{os.path.splitext(filename)[-1]}"))
            if not savepath.startswith(base_dir):
                return HttpResponse("only for post")
            with open(savepath, 'wb+') as wfile:
                for chunk in request.FILES[filename].chunks():
                    wfile.write(chunk)
            if isimage:
                from PIL import Image
                image = Image.open(savepath)
                image.save(savepath, quality=20, optimize=True)
            url = static(savepath)
            response.append(url)
        return HttpResponse(response)

    else:
        return HttpResponse("only for post")


# ===== 错误处理视图 =====
# 注意：这些函数保留是为了向后兼容
# 实际实现已经移动到 djangoblog.error_views
# 可以在 urls.py 中直接引用新的实现

from djangoblog.error_views import (
    page_not_found_view,
    server_error_view,
    permission_denied_view
)


def clean_cache_view(request):
    cache.clear()
    return HttpResponse('ok')


def feedback_submit_view(request):
    """处理用户反馈提交，带安全防护。"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    # Honeypot: 机器人会填写隐藏字段
    if request.POST.get('website', '').strip():
        return JsonResponse({'success': True})

    content = request.POST.get('content', '').strip()
    contact = request.POST.get('contact', '').strip()
    idempotency_key = request.POST.get('idempotency_key', '').strip()

    # 输入验证
    if not content or len(content) < 10:
        return JsonResponse({'error': '反馈内容至少需要10个字符'}, status=400)
    if len(content) > 2000:
        return JsonResponse({'error': '反馈内容不能超过2000个字符'}, status=400)
    if len(contact) > 200:
        return JsonResponse({'error': '联系方式不能超过200个字符'}, status=400)
    if not idempotency_key or len(idempotency_key) > 64:
        return JsonResponse({'error': '无效的请求标识'}, status=400)

    # 去除 HTML 标签
    content = re.sub(r'<[^>]+>', '', content)
    contact = re.sub(r'<[^>]+>', '', contact)

    # 频率限制: 每 IP 每小时 3 次
    from blog.traffic import get_client_ip
    from django.core.cache import cache as django_cache

    ip = get_client_ip(request)
    rate_key = f'feedback-rate:{ip}'
    current_count = django_cache.get(rate_key)
    if current_count is not None and current_count >= 3:
        return JsonResponse({'error': '提交过于频繁，请稍后再试'}, status=429)

    # 幂等性: 重复 key 静默返回成功
    if Feedback.objects.filter(idempotency_key=idempotency_key).exists():
        return JsonResponse({'success': True})

    Feedback.objects.create(
        content=content,
        contact=contact,
        ip_address=ip,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        referer=request.META.get('HTTP_REFERER', '')[:500],
        idempotency_key=idempotency_key,
    )

    # 递增频率计数
    if current_count is None:
        django_cache.set(rate_key, 1, 3600)
    else:
        try:
            django_cache.incr(rate_key)
        except ValueError:
            django_cache.set(rate_key, 1, 3600)

    return JsonResponse({'success': True})


def feedback_list_view(request):
    """内部接口: 查看所有反馈详情，token 保护。"""
    configured_token = getattr(settings, 'FEEDBACK_TOKEN', '')
    supplied_token = request.GET.get('token') or request.headers.get('X-Feedback-Token')
    if not configured_token or supplied_token != configured_token:
        raise Http404()

    try:
        limit = int(request.GET.get('limit', '100'))
    except ValueError:
        limit = 100
    limit = max(1, min(limit, 1000))

    feedbacks = Feedback.objects.all()
    total = feedbacks.count()
    rows = list(feedbacks.order_by('-created_at')[:limit])
    return JsonResponse({
        'total': total,
        'rows': [
            {
                'id': fb.id,
                'content': fb.content,
                'contact': fb.contact,
                'ip_address': fb.ip_address,
                'user_agent': fb.user_agent,
                'referer': fb.referer,
                'idempotency_key': fb.idempotency_key,
                'created_at': fb.created_at.isoformat(),
            }
            for fb in rows
        ],
    })


@csrf_exempt
def bookmark_stats_view(request):
    """返回站点统计：总浏览量 + 收藏人数。"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    total_views = Article.objects.filter(
        status='p'
    ).aggregate(total=Sum('views'))['total'] or 0

    bookmark_stat = BookmarkStat.get_singleton()

    return JsonResponse({
        'success': True,
        'total_views': total_views,
        'bookmark_count': bookmark_stat.bookmark_count,
    })


@csrf_exempt
def bookmark_add_view(request):
    """收藏计数 +1，同一 IP 每天限一次。"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    from blog.traffic import get_client_ip
    from django.core.cache import cache as django_cache

    ip = get_client_ip(request)
    rate_key = f'bookmark-rate:{ip}:{timezone.now().strftime("%Y-%m-%d")}'
    if django_cache.get(rate_key):
        bookmark_stat = BookmarkStat.get_singleton()
        return JsonResponse({
            'success': True,
            'bookmark_count': bookmark_stat.bookmark_count,
            'already_bookmarked': True,
        })

    BookmarkStat.objects.filter(pk=1).update(
        bookmark_count=F('bookmark_count') + 1
    )
    bookmark_stat = BookmarkStat.get_singleton()

    # 24h TTL，同一 IP 每天只 +1
    django_cache.set(rate_key, 1, 86400)

    return JsonResponse({
        'success': True,
        'bookmark_count': bookmark_stat.bookmark_count,
        'already_bookmarked': False,
    })
