from django.core.management.base import BaseCommand
from papers.services import ScheduledIngestionService
import time


class Command(BaseCommand):
    help = "Run automated incremental batch ingestion scheduler (once or as background daemon)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--daemon",
            action="store_true",
            help="Run as a continuous background daemon executing batches at interval.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=3600,
            help="Interval in seconds between daemon batches (default: 3600s / 1 hour).",
        )
        parser.add_argument(
            "--source",
            type=str,
            default="all",
            choices=["all", "openalex", "arxiv", "rss"],
            help="Source provider to ingest from (default: all).",
        )
        parser.add_argument(
            "--topic",
            type=str,
            default=None,
            help="Explicit topic to ingest for this batch.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Max records per source in this batch.",
        )

    def handle(self, *args, **options):
        is_daemon = options["daemon"]
        interval = options["interval"]
        source = options["source"]
        topic = options["topic"]
        limit = options["limit"]

        if not is_daemon:
            self.stdout.write(self.style.NOTICE(f"Running single scheduled ingestion batch for topic '{topic or 'auto-watermark'}'..."))
            log = ScheduledIngestionService.execute_scheduled_batch(source=source, topic=topic, batch_limit=limit)
            self.stdout.write(self.style.SUCCESS(
                f"Batch {log.id} finished: status={log.status}, fetched={log.records_fetched}, created={log.records_created}, updated={log.records_updated}, watermark={log.watermark}."
            ))
            return

        self.stdout.write(self.style.SUCCESS(f"Starting scheduled ingestion daemon (interval={interval}s)..."))
        while True:
            try:
                log = ScheduledIngestionService.execute_scheduled_batch(source=source, topic=topic, batch_limit=limit)
                self.stdout.write(self.style.SUCCESS(
                    f"[{log.started_at.strftime('%Y-%m-%d %H:%M:%S')}] Batch {log.id} status={log.status}: {log.records_created} created, {log.records_updated} updated (watermark: {log.watermark})."
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Daemon batch execution error: {e}"))
            time.sleep(interval)
