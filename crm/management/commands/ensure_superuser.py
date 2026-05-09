import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create or update a bootstrap superuser from environment variables.'

    def handle(self, *args, **options):
        username = (os.getenv('DJANGO_SUPERUSER_USERNAME') or '').strip()
        password = os.getenv('DJANGO_SUPERUSER_PASSWORD') or ''
        email = (os.getenv('DJANGO_SUPERUSER_EMAIL') or '').strip()

        if not username or not password:
            self.stdout.write(
                self.style.WARNING(
                    'Skipping bootstrap superuser creation because '
                    'DJANGO_SUPERUSER_USERNAME or DJANGO_SUPERUSER_PASSWORD is missing.'
                )
            )
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'is_staff': True,
                'is_superuser': True,
            },
        )

        changed_fields = []
        if email and user.email != email:
            user.email = email
            changed_fields.append('email')
        if not user.is_staff:
            user.is_staff = True
            changed_fields.append('is_staff')
        if not user.is_superuser:
            user.is_superuser = True
            changed_fields.append('is_superuser')

        user.set_password(password)
        changed_fields.append('password')

        if created:
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Created bootstrap superuser "{username}".'))
            return

        user.save(update_fields=changed_fields)
        self.stdout.write(self.style.SUCCESS(f'Updated bootstrap superuser "{username}".'))
