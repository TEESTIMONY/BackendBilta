from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import StaffProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_staff_profile(sender, instance, raw=False, **kwargs):
    if not raw and (instance.is_staff or instance.is_superuser):
        StaffProfile.objects.get_or_create(staff=instance)
