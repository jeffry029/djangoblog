import json
from django.utils.html import strip_tags
from django.utils import translation
from djangoblog.plugin_manage.base_plugin import BasePlugin
from djangoblog.plugin_manage import hooks
from blog.models import Article, Category, Tag
from djangoblog.utils import get_blog_setting


class SeoOptimizerPlugin(BasePlugin):
    PLUGIN_NAME = 'SEO 优化器'
    PLUGIN_DESCRIPTION = '为文章、页面等提供高级 SEO 优化，动态生成增强的 Open Graph 标签和 JSON-LD 结构化数据。基础 SEO（title、description、keywords）由视图层提供。'
    PLUGIN_VERSION = '0.3.0'
    PLUGIN_AUTHOR = 'liuangliangyy'

    def register_hooks(self):
        hooks.register('head_meta', self.dispatch_seo_generation)

    def _get_article_seo_data(self, context, request, blog_setting):
        article = context.get('article')
        if not isinstance(article, Article):
            return None

        from django.utils.html import escape
        from django.utils.text import Truncator
        from djangoblog.utils import CommonMarkdown
        
        article_title = article.get_title()
        article_body = article.get_body()
        article_category = article.category.get_name()
        site_name = blog_setting.get_site_name()

        if article.get_seo_description():
            description = article.get_seo_description()
        else:
            html_content = CommonMarkdown.get_markdown(article_body)
            description = strip_tags(html_content)
        description = ' '.join(description.split())
        description = Truncator(description).chars(150, truncate='...')
        description_escaped = escape(description)
        
        # 增强的 Open Graph 标签
        # 使用article.get_full_url确保与canonical一致
        article_url = article.get_full_url()
        meta_tags = f'''
        <meta property="og:type" content="article"/>
        <meta property="og:title" content="{escape(article_title)}"/>
        <meta property="og:description" content="{description_escaped}"/>
        <meta property="og:url" content="{article_url}"/>
        <meta property="article:published_time" content="{article.pub_time.isoformat()}"/>
        <meta property="article:modified_time" content="{article.last_modify_time.isoformat()}"/>
        <meta property="article:author" content="{escape(article.author.username)}"/>
        <meta property="article:section" content="{escape(article_category)}"/>
        '''
        for tag in article.tags.all():
            meta_tags += f'<meta property="article:tag" content="{escape(tag.get_name())}"/>'
        meta_tags += f'<meta property="og:site_name" content="{escape(site_name)}"/>'

        # JSON-LD 结构化数据
        first_image_url = article.get_first_image_url()
        structured_data = {
            "@context": "https://schema.org",
            "@type": "Article",
            "mainEntityOfPage": {"@type": "WebPage", "@id": article_url},
            "headline": article_title,
            "description": description,
            "datePublished": article.pub_time.isoformat(),
            "dateModified": article.last_modify_time.isoformat(),
            "author": {"@type": "Person", "name": article.author.username},
            "publisher": {"@type": "Organization", "name": site_name}
        }
        if first_image_url:
            structured_data["image"] = request.build_absolute_uri(first_image_url)

        return {
            "meta_tags": meta_tags,
            "json_ld": structured_data
        }

    def _get_category_seo_data(self, context, request, blog_setting):
        category_name = context.get('tag_name')  # 注意：这里沿用了原有的变量名
        if not category_name:
            return None
        
        category = Category.objects.filter(name=category_name).first() or Category.objects.filter(name_en=category_name).first()
        if not category:
            return None
        localized_category_name = category.get_name()

        # BreadcrumbList 结构化数据
        breadcrumb_items = [
            {"@type": "ListItem", "position": 1, "name": blog_setting.get_site_name(), "item": request.build_absolute_uri('/')},
            {"@type": "ListItem", "position": 2, "name": localized_category_name, "item": request.build_absolute_uri()}
        ]
        
        structured_data = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": breadcrumb_items
        }

        return {
            "meta_tags": "",
            "json_ld": structured_data
        }

    def _get_tag_seo_data(self, context, request, blog_setting):
        """标签页面的高级SEO数据"""
        tag_name = context.get('tag_name')
        if not tag_name:
            return None
        
        tag = Tag.objects.filter(name=tag_name).first()
        if not tag:
            return None

        # BreadcrumbList 结构化数据
        breadcrumb_items = [
            {"@type": "ListItem", "position": 1, "name": blog_setting.get_site_name(), "item": request.build_absolute_uri('/')},
            {"@type": "ListItem", "position": 2, "name": "Tags" if translation.get_language().startswith('en') else "标签", "item": request.build_absolute_uri('/tag/')},
            {"@type": "ListItem", "position": 3, "name": tag.get_name(), "item": request.build_absolute_uri()}
        ]
        
        structured_data = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": breadcrumb_items
        }

        return {
            "meta_tags": "",
            "json_ld": structured_data
        }

    def _get_author_seo_data(self, context, request, blog_setting):
        """作者页面的高级SEO数据"""
        author_name = context.get('tag_name')  # 注意：这里沿用了原有的变量名
        if not author_name:
            return None

        # BreadcrumbList 结构化数据
        breadcrumb_items = [
            {"@type": "ListItem", "position": 1, "name": blog_setting.get_site_name(), "item": request.build_absolute_uri('/')},
            {"@type": "ListItem", "position": 2, "name": "Authors" if translation.get_language().startswith('en') else "作者", "item": request.build_absolute_uri('/author/')},
            {"@type": "ListItem", "position": 3, "name": author_name, "item": request.build_absolute_uri()}
        ]
        
        structured_data = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": breadcrumb_items
        }

        return {
            "meta_tags": "",
            "json_ld": structured_data
        }

    def _get_default_seo_data(self, context, request, blog_setting):
        """首页和其他默认页面的高级SEO数据"""
        structured_data = {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": blog_setting.get_site_name(),
            "description": blog_setting.get_site_description(),
            "url": request.build_absolute_uri('/'),
            "potentialAction": {
                "@type": "SearchAction",
                "target": f"{request.build_absolute_uri('/search/')}?q={{search_term_string}}",
                "query-input": "required name=search_term_string"
            }
        }
        return {
            "meta_tags": "",
            "json_ld": structured_data
        }

    def dispatch_seo_generation(self, metas, context):
        """
        根据页面类型分发高级SEO生成
        注意：基础SEO（title、description、keywords）已由视图层提供
        此处只负责生成增强的 Open Graph 标签和 JSON-LD 结构化数据
        """
        request = context.get('request')
        if not request:
            return metas

        view_name = request.resolver_match.view_name
        blog_setting = get_blog_setting()
        
        seo_data = None
        if view_name == 'blog:detailbyid':
            seo_data = self._get_article_seo_data(context, request, blog_setting)
        elif view_name == 'blog:category_detail':
            seo_data = self._get_category_seo_data(context, request, blog_setting)
        elif view_name == 'blog:tag_detail':
            seo_data = self._get_tag_seo_data(context, request, blog_setting)
        elif view_name == 'blog:author_detail':
            seo_data = self._get_author_seo_data(context, request, blog_setting)
        
        if not seo_data:
            seo_data = self._get_default_seo_data(context, request, blog_setting)

        # 只生成 JSON-LD 和增强的 OG 标签
        json_ld_script = f'<script type="application/ld+json">{json.dumps(seo_data.get("json_ld", {}), ensure_ascii=False, indent=4)}</script>'

        seo_html = f"""
        {seo_data.get("meta_tags", "")}
        {json_ld_script}
        """
        
        # 将高级SEO内容追加到现有的metas内容上
        return metas + seo_html

plugin = SeoOptimizerPlugin()
