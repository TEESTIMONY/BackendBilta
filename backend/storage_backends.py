from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class SupabaseMediaStorage(S3Boto3Storage):
    default_acl = None
    file_overwrite = False

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('location', settings.SUPABASE_MEDIA_LOCATION)
        kwargs.setdefault('default_acl', None)
        kwargs.setdefault('file_overwrite', False)
        kwargs.setdefault('querystring_auth', settings.SUPABASE_STORAGE_QUERYSTRING_AUTH)
        super().__init__(*args, **kwargs)
