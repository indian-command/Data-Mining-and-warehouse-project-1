from django.core.management.base import BaseCommand
from papers.services import IngestionPipeline


class Command(BaseCommand):
    help = "Ingest external scholarly content from OpenAlex, arXiv, and RSS into MinIO and PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=str,
            default="all",
            choices=["all", "openalex", "arxiv", "rss"],
            help="Source provider to ingest from (default: all)",
        )
        parser.add_argument(
            "--query",
            type=str,
            default="artificial intelligence",
            help="Topic query string to search for",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Maximum number of records to fetch per source (default: 20)",
        )

    def handle(self, *args, **options):
        source = options["source"]
        query = options["query"]
        limit = options["limit"]

        self.stdout.write(self.style.NOTICE(
            f"Starting external content ingestion from '{source}' for query '{query}' (limit={limit})..."
        ))

        stats = IngestionPipeline.run_ingestion(source=source, query=query, limit=limit)

        self.stdout.write(self.style.SUCCESS(
            f"Ingestion completed successfully: {stats['created']} created, "
            f"{stats['updated']} updated (Total processed: {stats['total_processed']})."
        ))

