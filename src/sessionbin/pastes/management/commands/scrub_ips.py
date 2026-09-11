from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from sessionbin.pastes.models import Paste

IP_RETENTION_DAYS = 30


class Command(BaseCommand):
    help = (
        f"Clear uploader_ip on pastes older than {IP_RETENTION_DAYS} days. "
        "Nothing runs this automatically; wire it to a timer to enforce a retention window."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many rows would be scrubbed, without writing.",
        )

    def handle(self, *, dry_run, **options):
        cutoff = timezone.now() - timedelta(days=IP_RETENTION_DAYS)
        stale = Paste.objects.filter(created_at__lt=cutoff, uploader_ip__isnull=False)

        if dry_run:
            self.stdout.write(f"Would scrub {stale.count()} of {Paste.objects.count()} pastes.")
            return

        scrubbed = stale.update(uploader_ip=None)
        self.stdout.write(f"Scrubbed {scrubbed} of {Paste.objects.count()} pastes.")
