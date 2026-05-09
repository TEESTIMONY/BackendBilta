from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0004_staffinvitation'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='size_options',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
