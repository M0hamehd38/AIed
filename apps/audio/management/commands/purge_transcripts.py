from django.core.management.base import BaseCommand

from apps.audio.services import purge_expired


class Command(BaseCommand):
    help = 'Delete transcript lines past their retention period (run hourly).'

    def handle(self, *args, **opts):
        self.stdout.write(f'deleted {purge_expired()} expired transcript lines')
