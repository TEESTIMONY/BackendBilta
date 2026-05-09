from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0005_product_size_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='JobAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('file', models.FileField(upload_to='job_attachments/%Y/%m/%d/')),
                ('original_name', models.CharField(max_length=255)),
                ('content_type', models.CharField(blank=True, max_length=120)),
                ('size_bytes', models.PositiveBigIntegerField(default=0)),
                ('job', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='attachments', to='crm.job')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
    ]
