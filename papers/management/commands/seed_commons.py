from django.core.management.base import BaseCommand
from scripts.generate_synthetic import run_synthetic_generator


class Command(BaseCommand):
    help = "Seed Chanakya Research Commons with 500+ papers, 50+ members, 2000+ posts, 10000+ events and planted ground truth."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Launching synthetic generation pipeline..."))
        run_synthetic_generator()
        self.stdout.write(self.style.SUCCESS("Seeding process completed successfully."))

