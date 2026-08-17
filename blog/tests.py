import os
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.paginator import Paginator
from django.templatetags.static import static
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import BlogUser
from blog.forms import BlogSearchForm
from blog.models import Article, Category, Tag, SideBar, Links, NewsItem
from blog.services.collectors import collect_aihot_news, parse_aihot_items
from blog.templatetags.blog_tags import load_pagination_info, load_articletags, highlight_search_term, highlight_content
from djangoblog.utils import get_current_site, get_sha256
from oauth.models import OAuthUser, OAuthConfig


# Create your tests here.

class ArticleTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()

    def test_validate_article(self):
        site = get_current_site().domain
        user = BlogUser.objects.get_or_create(
            email="liangliangyy@gmail.com",
            username="liangliangyy")[0]
        user.set_password("liangliangyy")
        user.is_staff = True
        user.is_superuser = True
        user.save()
        response = self.client.get(user.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        response = self.client.get('/admin/servermanager/emailsendlog/')
        response = self.client.get('admin/admin/logentry/')
        s = SideBar()
        s.sequence = 1
        s.name = 'test'
        s.content = 'test content'
        s.is_enable = True
        s.save()

        category = Category()
        category.name = "category"
        category.creation_time = timezone.now()
        category.last_mod_time = timezone.now()
        category.save()

        tag = Tag()
        tag.name = "nicetag"
        tag.save()

        article = Article()
        article.title = "nicetitle"
        article.body = "nicecontent"
        article.author = user
        article.category = category
        article.type = 'a'
        article.status = 'p'

        article.save()
        self.assertGreaterEqual(article.views, 10)
        self.assertLessEqual(article.views, 30)
        self.assertEqual(0, article.tags.count())
        article.tags.add(tag)
        article.save()
        self.assertEqual(1, article.tags.count())

        for i in range(20):
            article = Article()
            article.title = "nicetitle" + str(i)
            article.body = "nicetitle" + str(i)
            article.author = user
            article.category = category
            article.type = 'a'
            article.status = 'p'
            article.save()
            article.tags.add(tag)
            article.save()
        from blog.documents import ELASTICSEARCH_ENABLED
        if ELASTICSEARCH_ENABLED:
            call_command("build_index")
            response = self.client.get('/search', {'q': 'nicetitle'})
            self.assertEqual(response.status_code, 200)

        response = self.client.get(article.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        from djangoblog.spider_notify import SpiderNotify
        SpiderNotify.notify(article.get_absolute_url())
        response = self.client.get(tag.get_absolute_url())
        self.assertEqual(response.status_code, 200)

        response = self.client.get(category.get_absolute_url())
        self.assertEqual(response.status_code, 200)

        response = self.client.get('/search', {'q': 'django'})
        self.assertEqual(response.status_code, 200)
        s = load_articletags(article)
        self.assertIsNotNone(s)

        self.client.login(username='liangliangyy', password='liangliangyy')

        response = self.client.get(reverse('blog:archives'))
        self.assertEqual(response.status_code, 200)

        p = Paginator(Article.objects.all(), settings.PAGINATE_BY)
        self.check_pagination(p, '', '')

        p = Paginator(Article.objects.filter(tags=tag), settings.PAGINATE_BY)
        self.check_pagination(p, '分类标签归档', tag.slug)

        p = Paginator(
            Article.objects.filter(
                author__username='liangliangyy'), settings.PAGINATE_BY)
        self.check_pagination(p, '作者文章归档', 'liangliangyy')

        p = Paginator(Article.objects.filter(category=category), settings.PAGINATE_BY)
        self.check_pagination(p, '分类目录归档', category.slug)

        f = BlogSearchForm()
        f.search()
        # self.client.login(username='liangliangyy', password='liangliangyy')
        from djangoblog.spider_notify import SpiderNotify
        SpiderNotify.baidu_notify([article.get_full_url()])

        from blog.templatetags.blog_tags import gravatar_url, gravatar
        u = gravatar_url('liangliangyy@gmail.com')
        u = gravatar('liangliangyy@gmail.com')

        link = Links(
            sequence=1,
            name="lylinux",
            link='https://wwww.lylinux.net')
        link.save()
        response = self.client.get('/links.html')
        self.assertEqual(response.status_code, 200)

        response = self.client.get('/feed/')
        self.assertEqual(response.status_code, 200)

        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)

        self.client.get("/admin/blog/article/1/delete/")
        self.client.get('/admin/servermanager/emailsendlog/')
        self.client.get('/admin/admin/logentry/')
        self.client.get('/admin/admin/logentry/1/change/')

    def check_pagination(self, p, type, value):
        for page in range(1, p.num_pages + 1):
            s = load_pagination_info(p.page(page), type, value)
            self.assertIsNotNone(s)
            if s['previous_url']:
                response = self.client.get(s['previous_url'])
                self.assertEqual(response.status_code, 200)
            if s['next_url']:
                response = self.client.get(s['next_url'])
                self.assertEqual(response.status_code, 200)

    def test_image(self):
        import requests
        rsp = requests.get(
            'https://www.python.org/static/img/python-logo.png')
        imagepath = os.path.join(settings.BASE_DIR, 'python.png')
        with open(imagepath, 'wb') as file:
            file.write(rsp.content)
        rsp = self.client.post('/upload')
        self.assertEqual(rsp.status_code, 403)
        sign = get_sha256(get_sha256(settings.SECRET_KEY))
        with open(imagepath, 'rb') as file:
            imgfile = SimpleUploadedFile(
                'python.png', file.read(), content_type='image/jpg')
            form_data = {'python.png': imgfile}
            rsp = self.client.post(
                '/upload?sign=' + sign, form_data, follow=True)
            self.assertEqual(rsp.status_code, 200)
        os.remove(imagepath)
        from djangoblog.utils import save_user_avatar, send_email
        send_email(['qq@qq.com'], 'testTitle', 'testContent')
        save_user_avatar(
            'https://www.python.org/static/img/python-logo.png')

    def test_errorpage(self):
        rsp = self.client.get('/eee')
        self.assertEqual(rsp.status_code, 404)

    def test_commands(self):
        user = BlogUser.objects.get_or_create(
            email="liangliangyy@gmail.com",
            username="liangliangyy")[0]
        user.set_password("liangliangyy")
        user.is_staff = True
        user.is_superuser = True
        user.save()

        c = OAuthConfig()
        c.type = 'qq'
        c.appkey = 'appkey'
        c.appsecret = 'appsecret'
        c.save()

        u = OAuthUser()
        u.type = 'qq'
        u.openid = 'openid'
        u.user = user
        u.picture = static("/blog/img/avatar.png")
        u.metadata = '''
{
"figureurl": "https://qzapp.qlogo.cn/qzapp/101513904/C740E30B4113EAA80E0D9918ABC78E82/30"
}'''
        u.save()

        u = OAuthUser()
        u.type = 'qq'
        u.openid = 'openid1'
        u.picture = 'https://qzapp.qlogo.cn/qzapp/101513904/C740E30B4113EAA80E0D9918ABC78E82/30'
        u.metadata = '''
        {
       "figureurl": "https://qzapp.qlogo.cn/qzapp/101513904/C740E30B4113EAA80E0D9918ABC78E82/30"
        }'''
        u.save()

        from blog.documents import ELASTICSEARCH_ENABLED
        if ELASTICSEARCH_ENABLED:
            call_command("build_index")
        call_command("ping_baidu", "all")
        call_command("create_testdata")
        call_command("clear_cache")
        call_command("sync_user_avatar")
        call_command("build_search_words")


class EditorialRedesignTemplateTest(TestCase):
    def setUp(self):
        self.user = BlogUser.objects.create_user(
            username="editor",
            email="editor@example.com",
            password="password123",
        )
        self.category = Category.objects.create(name="后端技术")
        self.tag = Tag.objects.create(name="Django")
        self.article = Article.objects.create(
            title="Django 架构实践",
            body="这是一篇关于 Django 博客架构实践的文章。",
            author=self.user,
            category=self.category,
            type="a",
            status="p",
        )
        self.article.tags.add(self.tag)
        self.next_article = Article.objects.create(
            title="FastAPI 部署实践",
            body="这是一篇关于 FastAPI 服务部署的文章。",
            author=self.user,
            category=self.category,
            type="a",
            status="p",
        )
        self.next_article.tags.add(self.tag)

    def test_index_uses_editorial_redesign_structure(self):
        response = self.client.get(reverse("blog:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "editorial-shell")
        self.assertContains(response, "editorial-list-shell")
        self.assertContains(response, "editorial-article-card")
        self.assertNotContains(response, "editorial-sidebar")
        self.assertNotContains(response, "热门文章")
        self.assertContains(response, "djangoblog-theme")
        self.assertNotContains(response, "prefers-color-scheme: dark').matches")

    def test_article_detail_uses_editorial_redesign_structure(self):
        response = self.client.get(self.article.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "editorial-detail-card")
        self.assertContains(response, "editorial-article-body")
        self.assertContains(response, "editorial-post-nav")

    def test_navigation_hides_archive_and_shows_news(self):
        response = self.client.get(reverse("blog:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("blog:news"))
        self.assertContains(response, "新闻")
        self.assertNotContains(response, "归档")


class NewsFeatureTest(TestCase):
    def test_news_page_lists_visible_news(self):
        NewsItem.objects.create(
            title="AI 框架发布新版本",
            summary="新版本改进了推理性能。",
            content="<p>新版本详细内容。</p>",
            reason="适合关注 AI 服务部署。",
            source_name="AI HOT",
            source_url="https://example.com/news/1",
            tags="AI,框架",
            is_visible=True,
        )
        NewsItem.objects.create(
            title="隐藏新闻",
            source_url="https://example.com/news/2",
            is_visible=False,
        )

        response = self.client.get(reverse("blog:news"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI 框架发布新版本")
        self.assertContains(response, "适合关注 AI 服务部署。")
        self.assertContains(response, "editorial-list-shell")
        self.assertContains(response, "editorial-news-summary")
        self.assertNotContains(response, "editorial-sidebar")
        self.assertNotContains(response, "热门文章")
        self.assertNotContains(response, "近期文章")
        self.assertNotContains(response, "隐藏新闻")
        visible_item = NewsItem.objects.get(title="AI 框架发布新版本")
        self.assertContains(response, f'href="{visible_item.get_absolute_url()}"')
        self.assertNotContains(
            response,
            f'href="{visible_item.get_absolute_url()}" target="_blank"',
        )

    def test_news_without_content_keeps_collected_external_link(self):
        item = NewsItem.objects.create(
            title="Summary only news",
            summary="Summary only.",
            content="<p> </p>",
            source_url="https://aihot.virxact.com/items/summary-only",
        )

        response = self.client.get(reverse("blog:news"))

        self.assertEqual(item.get_display_url(), item.source_url)
        self.assertContains(response, f'href="{item.source_url}"')
        self.assertContains(response, 'target="_blank" rel="noopener nofollow"')

    def test_news_detail_displays_collected_content_and_source_links(self):
        item = NewsItem.objects.create(
            title="Agent 运行时发布",
            summary="一段 AI 摘要。",
            content='<p>本站内展示的正文。</p><script>alert("bad")</script>',
            source_name="Example Engineering",
            source_url="https://aihot.virxact.com/items/agent-runtime",
            original_url="https://example.com/agent-runtime",
            tags="AI 产品",
            is_visible=True,
        )

        response = self.client.get(item.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agent 运行时发布")
        self.assertContains(response, "本站内展示的正文。")
        self.assertContains(response, item.original_url)
        self.assertContains(response, item.source_url)
        self.assertNotContains(response, '<script>alert("bad")</script>')

    def test_legacy_news_source_url_is_treated_as_original_link(self):
        item = NewsItem.objects.create(
            title="Legacy news",
            source_url="https://x.com/example/status/1",
        )

        self.assertEqual(item.get_original_url(), item.source_url)
        self.assertEqual(item.get_aihot_url(), '')
        self.assertEqual(item.get_display_url(), item.source_url)

    def test_hidden_news_detail_returns_404(self):
        item = NewsItem.objects.create(
            title="隐藏新闻",
            source_url="https://aihot.virxact.com/items/hidden",
            is_visible=False,
        )

        response = self.client.get(item.get_absolute_url())

        self.assertEqual(response.status_code, 404)

    @patch('blog.services.collectors.fetch_url')
    def test_collect_aihot_news_stores_feed_content(self, fetch_url_mock):
        fetch_url_mock.return_value = self.aihot_feed_xml()

        result = collect_aihot_news(limit=1)

        self.assertEqual((result.created, result.skipped, result.failed), (1, 0, 0))
        item = NewsItem.objects.get(title='Collected news')
        self.assertEqual(item.original_url, 'https://example.com/collected')
        self.assertEqual(item.content, '<p>Collected body.</p>')

    @patch('blog.services.collectors.fetch_url')
    def test_collect_aihot_news_updates_pre_detail_link_without_duplicate(self, fetch_url_mock):
        legacy = NewsItem.objects.create(
            title='Old title',
            source_url='https://example.com/collected',
            tags='Existing tag',
        )
        fetch_url_mock.return_value = self.aihot_feed_xml()

        result = collect_aihot_news(limit=1)

        self.assertEqual((result.created, result.skipped, result.failed), (0, 1, 0))
        self.assertEqual(NewsItem.objects.count(), 1)
        legacy.refresh_from_db()
        self.assertEqual(legacy.source_url, 'https://aihot.virxact.com/items/collected')
        self.assertEqual(legacy.original_url, 'https://example.com/collected')
        self.assertEqual(legacy.content, '<p>Collected body.</p>')
        self.assertEqual(legacy.tags, 'Existing tag')

    @staticmethod
    def aihot_feed_xml():
        return """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
          <channel><item>
            <title>Collected news</title>
            <link>https://aihot.virxact.com/items/collected</link>
            <description><![CDATA[Collected summary.

阅读原文：https://example.com/collected]]></description>
            <content:encoded><![CDATA[<p>Collected body.</p>]]></content:encoded>
            <category>AI 模型</category>
            <pubDate>Fri, 17 Jul 2026 00:40:20 GMT</pubDate>
            <author>noreply@aihot.virxact.com (Example Source)</author>
          </item></channel>
        </rss>"""

    def test_parse_aihot_items_extracts_linked_cards(self):
        html = """
        <article>
            <a href="/item/1">LangGraph 发布更新</a>
            <span class="tag">AI</span>
            <p>面向 agent 服务编排。</p>
        </article>
        """

        items = parse_aihot_items(html, base_url="https://aihot.virxact.com/")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "LangGraph 发布更新")
        self.assertEqual(items[0]["source_url"], "https://aihot.virxact.com/item/1")
        self.assertIn("AI", items[0]["tags"])

    def test_title_search_returns_articles_and_news(self):
        user = BlogUser.objects.create_user(username="searcher", email="searcher@example.com")
        category, _ = Category.objects.get_or_create(name="文章")
        Article.objects.create(
            title="Python 性能调优实践",
            body="content",
            author=user,
            category=category,
            type="a",
            status="p",
        )
        NewsItem.objects.create(
            title="Python 3.14 发布",
            source_url="https://example.com/python-news",
            source_url_hash="python-news",
            is_visible=True,
        )

        response = self.client.get("/search", {"q": "Python"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<mark>Python</mark>", html=False)
        self.assertContains(response, "性能调优实践")
        self.assertContains(response, "3.14 发布")
        self.assertContains(response, 'href="https://example.com/python-news"')
        self.assertContains(response, 'target="_blank" rel="noopener nofollow"')


class SearchHighlightTest(TestCase):
    """测试搜索高亮功能"""

    def test_highlight_search_term_filter(self):
        """测试标题高亮filter"""
        # 测试基本高亮
        text = "Django is a web framework"
        result = highlight_search_term(text, "django")
        self.assertIn("<mark>Django</mark>", result)
        self.assertIn("web framework", result)

        # 测试不区分大小写
        text = "Python and python"
        result = highlight_search_term(text, "PYTHON")
        self.assertEqual(result.count("<mark>"), 2)

        # 测试多个关键词
        text = "Django web framework with Python"
        result = highlight_search_term(text, "django python")
        self.assertIn("<mark>Django</mark>", result)
        self.assertIn("<mark>Python</mark>", result)

        # 测试空查询
        text = "Some text"
        result = highlight_search_term(text, "")
        self.assertEqual(result, text)

        # 测试空文本
        result = highlight_search_term("", "query")
        self.assertEqual(result, "")

    def test_highlight_content_filter(self):
        """测试正文高亮filter"""
        # 测试HTML内容高亮
        html = "<p>Django is a great web framework. Django makes development easy.</p>"
        result = highlight_content(html, "django")

        # 应该包含高亮标记
        self.assertIn("<mark>", result)
        self.assertIn("</mark>", result)

        # HTML标签应该被去除
        self.assertNotIn("<p>", result)

        # 应该包含Django关键词（不区分大小写）
        self.assertIn("django", result.lower())

        # 测试空查询
        result = highlight_content(html, "")
        self.assertEqual(result, html)

    def test_search_page_access(self):
        """测试搜索页面访问"""
        # 测试搜索页面可以正常访问
        response = self.client.get('/search', {'q': 'django'})
        self.assertEqual(response.status_code, 200)

        # 检查响应中是否有查询参数
        self.assertIn('query', response.context)
        self.assertEqual(response.context['query'], 'django')

    def test_chinese_keyword_highlight(self):
        """测试中文关键词高亮"""
        text = "这是一个Django博客系统"
        result = highlight_search_term(text, "Django")
        self.assertIn("<mark>Django</mark>", result)

        # 测试中文关键词
        text = "欢迎使用DjangoBlog系统"
        result = highlight_search_term(text, "Django")
        self.assertIn("<mark>Django</mark>", result)
