from django.contrib.auth import get_user_model
from django.contrib.syndication.views import Feed
from django.utils import timezone
from django.utils.feedgenerator import Rss201rev2Feed
from django.utils.translation import gettext as _

from blog.models import Article
from djangoblog.utils import CommonMarkdown


class DjangoBlogFeed(Feed):
    feed_type = Rss201rev2Feed

    link = "/feed/"

    def title(self):
        return _('Developer Radar')

    def description(self):
        return _('AI-curated technical articles, programming practices, and artificial intelligence news.')

    def author_name(self):
        return get_user_model().objects.first().nickname

    def author_link(self):
        return get_user_model().objects.first().get_absolute_url()

    def items(self):
        return Article.objects.filter(type='a', status='p').order_by('-pub_time')[:5]

    def item_title(self, item):
        return item.get_title()

    def item_description(self, item):
        return CommonMarkdown.get_markdown(item.get_body())

    def feed_copyright(self):
        now = timezone.now()
        return "Copyright© {year} {site_name}".format(year=now.year, site_name=self.title())

    def item_link(self, item):
        return item.get_absolute_url()

    def item_guid(self, item):
        return
