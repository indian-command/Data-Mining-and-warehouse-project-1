from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from papers.models import Paper, PaperChunk
from papers.services import EmbeddingService
from research_assistant.services import ResearchAssistantService

User = get_user_model()


class ResearchAssistantTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="assistant_user", email="asst@example.com", password="Pass123!"
        )
        self.paper = Paper.objects.create(
            title="AlphaFold: Highly Accurate Protein Structure Prediction",
            canonical_doi="10.1038/s41586-021-03819-2",
            authors=["John Jumper", "Demis Hassabis"],
            abstract="Predicts 3D coordinates of all heavy atoms for a given protein from its sequence.",
            published_year=2021,
            sources=["nature"],
        )
        emb = EmbeddingService.generate_embedding(
            "Predicts 3D coordinates of all heavy atoms for a given protein from its sequence."
        )
        self.chunk = PaperChunk.objects.create(
            paper=self.paper,
            chunk_index=0,
            chunk_text="AlphaFold accurately predicts 3D coordinates of heavy atoms for any protein sequence directly.",
            embedding=emb,
        )

    def test_research_assistant_grounded_answer(self):
        res = ResearchAssistantService.ask("How does AlphaFold predict protein coordinates?", user=self.user)
        self.assertIn("answer", res)
        self.assertIn("sources", res)
        self.assertTrue(res["grounded"])
        self.assertTrue(len(res["sources"]) > 0)
        # Verify citation badge [1] is present in answer
        self.assertIn("[1]", res["answer"])
        # Verify source metadata
        first_src = res["sources"][0]
        self.assertEqual(first_src["paper_id"], self.paper.id)
        self.assertEqual(first_src["citation_id"], 1)

    def test_assistant_view(self):
        resp = self.client.get(reverse("research_assistant:assistant"), {"q": "protein structure"})
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "research_assistant/assistant.html")
        self.assertContains(resp, "AlphaFold")
