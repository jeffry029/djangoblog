from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0014_publictrafficdailystat'),
    ]

    operations = [
        migrations.AddField(
            model_name='blogsettings',
            name='show_api_promo',
            field=models.BooleanField(default=False, verbose_name='是否显示 API 中转推广'),
        ),
    ]
