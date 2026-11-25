from django.core.management.base import BaseCommand
from scripts.evaluate import run_evaluation_suite


class Command(BaseCommand):
    help = "Run the quantitative evaluation suite and print benchmark metrics against planted ground truth."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting model and subsystem evaluation suite..."))
        run_evaluation_suite()
        self.stdout.write(self.style.SUCCESS("Evaluation completed successfully."))

