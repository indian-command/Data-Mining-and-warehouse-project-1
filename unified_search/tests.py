from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from papers.models import Paper
from research_library.models import ResearchResource
from discussions.models import DiscussionPost
from accounts.models import Department, Profile, Topic
from unified_search.services import EntityResolver, UnifiedSearchService

User = get_user_model()


class UnifiedSearchTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="search_user",
            email="search@example.com",
            password="TestPassword123!",
        )
        self.dept = Department.objects.create(name="Computer Science & AI", code="CSAI")
        self.profile = Profile.objects.create(
            user=self.user, department=self.dept, research_interests="Deep learning and NLP"
        )
        self.topic = Topic.objects.create(name="Artificial Intelligence")

        self.paper = Paper.objects.create(
            title="Transformer Networks for Language Translation",
            canonical_doi="10.1145/trans.1",
            arxiv_id="1706.03762",
            authors=["Vaswani et al."],
            abstract="Self-attention mechanisms in neural translation.",
            published_year=2017,
            sources=["arxiv"],
            pagerank_score=0.08,
        )

        self.resource = ResearchResource.objects.create(
            title="Transformer Networks Architecture Guide",
            description="Reference notes on attention layers.",
            resource_type="link",
            url="https://example.org/transformers",
            uploaded_by=self.user,
        )

        self.post = DiscussionPost.objects.create(
            author=self.user,
            title="Discussion on Transformer Scaling Laws",
            content="Empirical observations regarding model capacity and batch size.",
        )
        self.post.tags.add(self.topic)

    def test_entity_resolver_exact_doi_match(self):
        # Two records with exact same DOI but different sources
        rec1 = {
            "id": 1,
            "canonical_doi": "10.1145/dup.test",
            "title": "Machine Learning Foundations",
            "abstract": "First version.",
            "sources": ["arxiv"],
            "score": 0.8,
        }
        rec2 = {
            "id": 2,
            "canonical_doi": "10.1145/dup.test",
            "title": "Machine Learning Foundations (Extended)",
            "abstract": "First version with extended proofs.",
            "sources": ["openalex"],
            "score": 0.9,
        }
        deduped = EntityResolver.resolve_and_deduplicate([rec1, rec2])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(sorted(deduped[0]["sources"]), ["arxiv", "openalex"])
        self.assertEqual(deduped[0]["score"], 0.9)

    def test_entity_resolver_minhash_near_duplicate(self):
        # Near duplicate texts without DOI
        text = "Deep reinforcement learning for autonomous continuous robot control."
        rec1 = {
            "id": 10,
            "title": "Deep Reinforcement Learning for Autonomous Continuous Robot Control",
            "abstract": text,
            "sources": ["arxiv"],
            "score": 0.85,
        }
        rec2 = {
            "id": 11,
            "title": "Deep Reinforcement Learning for Autonomous Continuous Robot Control.",
            "abstract": text + " Validated across MuJoCo environments.",
            "sources": ["rss"],
            "score": 0.88,
        }
        deduped = EntityResolver.resolve_and_deduplicate([rec1, rec2])
        self.assertEqual(len(deduped), 1)
        self.assertIn("arxiv", deduped[0]["sources"])
        self.assertIn("rss", deduped[0]["sources"])

    def test_4_panel_search_execution(self):
        results = UnifiedSearchService.execute_unified_search("Transformer", user=self.user)
        self.assertIn("scholarly_sources", results)
        self.assertIn("library_resources", results)
        self.assertIn("university_members", results)
        self.assertIn("discussions", results)

        self.assertTrue(len(results["scholarly_sources"]) > 0)
        self.assertTrue(len(results["library_resources"]) > 0)
        self.assertTrue(len(results["discussions"]) > 0)

    def test_unified_search_view(self):
        resp = self.client.get(reverse("unified_search:search"), {"q": "Transformer"})
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "unified_search/search.html")
        self.assertContains(resp, "Transformer Networks for Language Translation")
