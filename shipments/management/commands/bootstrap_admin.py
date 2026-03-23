import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the SILVERLINE backend admin account."

    def handle(self, *args, **options):
        user_model = get_user_model()
        email = os.getenv("ADMIN_EMAIL", "smithlinda99360@gmail.com").strip()
        password = os.getenv("ADMIN_PASSWORD", "Admin2026").strip()

        admin_user, created = user_model.objects.get_or_create(
            username=email,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )

        changed = False
        if admin_user.email != email:
            admin_user.email = email
            changed = True
        if not admin_user.is_staff:
            admin_user.is_staff = True
            changed = True
        if not admin_user.is_superuser:
            admin_user.is_superuser = True
            changed = True

        admin_user.set_password(password)
        changed = True

        if created or changed:
            admin_user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} admin user: {email}"))
