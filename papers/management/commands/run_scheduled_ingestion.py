import time
import logging
from django.core.management.base import BaseCommand
from papers.services import ScheduledIngestionService, IngestionPipeline
from institutional_analytics.services import StarSchemaETLService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Automated scheduled batch ingestion: periodically triggers scholarly ingestion "
        "(OpenAlex, arXiv, RSS), refreshes citation PageRank, and updates the Star Schema Parquet warehouse."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--daemon",
            action="store_true",
            help="Run as a continuous background daemon executing batches at specified interval.",
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
            help="Explicit research topic (defaults to rotating watermark).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=15,
            help="Max records per source in this batch (default: 15).",
        )
        parser.add_argument(
            "--skip-etl",
            action="store_true",
            help="Skip regenerating Star Schema Parquet warehouse after ingestion.",
        )

    def _execute_cycle(self, source, topic, limit, skip_etl):
        # 1. Scholarly Ingestion
        self.stdout.write(self.style.NOTICE(
            f"--> Ingesting from scholarly providers (source='{source}', topic='{topic or 'auto-watermark'}', limit={limit})..."
        ))
        log = ScheduledIngestionService.execute_scheduled_batch(source=source, topic=topic, batch_limit=limit)

        self.stdout.write(self.style.SUCCESS(
            f"    Batch #{log.id}: status={log.status}, fetched={log.records_fetched}, "
            f"created={log.records_created}, updated={log.records_updated}, watermark='{log.watermark}'."
        ))

        # 2. PageRank Recomputation
        self.stdout.write(self.style.NOTICE("--> Recomputing citation graph PageRank..."))
        pr_count = IngestionPipeline.recompute_pagerank()
        self.stdout.write(self.style.SUCCESS(f"    PageRank recomputed across {pr_count} publications."))

        # 3. Star Schema Parquet Warehouse Synchronization
        if not skip_etl:
            self.stdout.write(self.style.NOTICE("--> Synchronizing analytical Star Schema Parquet tables..."))
            try:
                paths = StarSchemaETLService.run_etl()
                self.stdout.write(self.style.SUCCESS(
                    f"    Parquet Warehouse refreshed ({len(paths)} tables synchronized in MinIO and local storage)."
                ))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"    Parquet ETL warning: {e}"))

        return log

    def handle(self, *args, **options):
        is_daemon = options["daemon"]
        interval = options["interval"]
        source = options["source"]
        topic = options["topic"]
        limit = options["limit"]
        skip_etl = options["skip_etl"]

        if not is_daemon:
            self.stdout.write(self.style.HTTP_INFO("=== Running Scheduled Batch Ingestion (Single Run) ==="))
            self._execute_cycle(source, topic, limit, skip_etl)
            self.stdout.write(self.style.SUCCESS("=== Scheduled Ingestion Cycle Complete ==="))
            return

        self.stdout.write(self.style.HTTP_INFO(
            f"=== Starting Scheduled Ingestion Daemon (Interval: {interval}s) ==="
        ))
        while True:
            try:
                self._execute_cycle(source, topic, limit, skip_etl)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Daemon cycle error: {e}"))
                logger.exception("Scheduled ingestion daemon failure")

            self.stdout.write(self.style.NOTICE(f"Sleeping for {interval}s until next scheduled batch..."))
            time.sleep(interval)
