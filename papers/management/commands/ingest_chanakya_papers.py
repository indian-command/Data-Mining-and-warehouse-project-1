from django.core.management.base import BaseCommand
from papers.services import ChanakyaUniversityIngester


class Command(BaseCommand):
    help = "Politely scrape and ingest real Chanakya University research publications from chanakyauniversity.edu.in following ELT architecture."

    def add_arguments(self, parser):
        parser.add_argument(
            "--faculty-limit",
            type=int,
            default=50,
            help="Maximum number of faculty profiles to crawl (default: 50)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=300,
            help="Maximum number of publications to process (default: 300)",
        )

    def handle(self, *args, **options):
        faculty_limit = options["faculty_limit"]
        batch_size = options["batch_size"]

        self.stdout.write(self.style.NOTICE(
            f"Starting polite Chanakya University publication ingestion (faculty_limit={faculty_limit}, batch_size={batch_size})..."
        ))

        stats = ChanakyaUniversityIngester.ingest(faculty_limit=faculty_limit, batch_size=batch_size)

        self.stdout.write(self.style.SUCCESS(
            f"\nChanakya University Ingestion Summary:\n"
            f"  - Total Processed     : {stats['total_processed']}\n"
            f"  - Newly Ingested      : {stats['created']}\n"
            f"  - Deduplicated/Merged : {stats['deduplicated']}\n"
            f"  - Total Papers in DB  : {stats['total_papers']}\n"
            f"  - Total RAG Chunks    : {stats['total_chunks']}\n"
            f"  - Shared Library Items: {stats['total_library_items']}"
        ))
