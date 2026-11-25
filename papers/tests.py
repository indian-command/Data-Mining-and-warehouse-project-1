from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from papers.models import Paper, PaperChunk, PaperCitation
from papers.services import EmbeddingService, TextChunker, IngestionPipeline
from research_library.models import ResearchResource

User = get_user_model()


class PapersModelAndServicesTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="paper_tester",
            email="tester@example.com",
            password="TestPassword123!",
        )

    def test_paper_creation_and_properties(self):
        paper = Paper.objects.create(
            title="Foundations of Machine Learning",
            canonical_doi="10.1145/test.ml.1",
            arxiv_id="2401.0001",
            authors=["Alice Smith", "Bob Jones"],
            abstract="An introduction to statistical learning algorithms.",
            published_year=2024,
            sources=["arxiv", "openalex"],
        )
        self.assertEqual(paper.authors_display, "Alice Smith, Bob Jones")
        self.assertEqual(paper.sources, ["arxiv", "openalex"])
        self.assertIn("Foundations of Machine Learning", str(paper))

    def test_embedding_service_dimensions(self):
        vec = EmbeddingService.generate_embedding("Natural language processing with transformers.")
        self.assertEqual(len(vec), 384)
        self.assertTrue(all(isinstance(x, float) for x in vec))

    def test_text_chunker(self):
        long_text = " ".join([f"word{i}" for i in range(350)])
        chunks = TextChunker.chunk_text(long_text, chunk_size_words=100, overlap_words=20)
        self.assertGreater(len(chunks), 2)
        # Verify overlap exists
        words_first = set(chunks[0].split())
        words_second = set(chunks[1].split())
        self.assertTrue(len(words_first & words_second) > 0)

    def test_ingestion_pipeline_incremental_refresh(self):
        data = {
            "canonical_doi": "10.1234/incremental.test",
            "title": "Incremental Paper Test",
            "abstract": "Testing deduplication on ingestion.",
            "authors": ["Researcher A"],
            "published_year": 2024,
            "sources": ["openalex"],
        }
        # First save
        paper1, created1 = IngestionPipeline.save_paper_record(data, default_user=self.user)
        self.assertTrue(created1)
        self.assertEqual(Paper.objects.filter(canonical_doi="10.1234/incremental.test").count(), 1)

        # Second save with same DOI but new source
        data2 = dict(data)
        data2["sources"] = ["arxiv"]
        paper2, created2 = IngestionPipeline.save_paper_record(data2, default_user=self.user)
        self.assertFalse(created2)
        self.assertEqual(paper1.id, paper2.id)
        # Sources should be merged
        paper2.refresh_from_db()
        self.assertIn("openalex", paper2.sources)
        self.assertIn("arxiv", paper2.sources)

    def test_paper_views(self):
        paper = Paper.objects.create(
            title="Deep Learning in Vision",
            canonical_doi="10.1145/vision.1",
            authors=["Carol White"],
            abstract="Convolutional models.",
            published_year=2023,
        )
        # List view
        resp = self.client.get(reverse("papers:paper_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Deep Learning in Vision")

        # Detail view
        resp = self.client.get(reverse("papers:paper_detail", args=[paper.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Deep Learning in Vision")

        # Save view (authenticated)
        self.client.force_login(self.user)
        save_resp = self.client.post(reverse("papers:save_paper", args=[paper.id]))
        self.assertEqual(save_resp.status_code, 302)
        paper.refresh_from_db()
        self.assertGreaterEqual(paper.save_count, 1)
