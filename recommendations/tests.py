from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from accounts.models import Department, Profile, Topic
from papers.models import Paper
from research_library.models import ResearchResource, SavedResearchItem
from recommendations.services import RecommendationService

User = get_user_model()


class RecommendationTests(TestCase):

    def setUp(self):
        self.dept = Department.objects.create(name="Data Science & Analytics", code="DSA")
        self.topic = Topic.objects.create(name="Deep Learning")

        self.user1 = User.objects.create_user(username="rec_user_1", email="u1@example.com", password="Pass123!")
        self.p1 = Profile.objects.create(user=self.user1, department=self.dept)
        self.p1.topics.add(self.topic)

        self.user2 = User.objects.create_user(username="rec_user_2", email="u2@example.com", password="Pass123!")
        self.p2 = Profile.objects.create(user=self.user2, department=self.dept)
        self.p2.topics.add(self.topic)

        self.paper1 = Paper.objects.create(
            title="Scalable Deep Learning Architectures",
            canonical_doi="10.1145/rec.1",
            published_year=2024,
            pagerank_score=0.05,
            save_count=3,
        )
        self.res1 = ResearchResource.objects.create(
            title=self.paper1.title,
            resource_type="link",
            doi=self.paper1.canonical_doi,
            uploaded_by=self.user1,
        )
        self.paper1.resource = self.res1
        self.paper1.save()

        self.paper2 = Paper.objects.create(
            title="Graph Representation Learning Advances",
            canonical_doi="10.1145/rec.2",
            published_year=2024,
            pagerank_score=0.04,
            save_count=5,
        )
        self.res2 = ResearchResource.objects.create(
            title=self.paper2.title,
            resource_type="link",
            doi=self.paper2.canonical_doi,
            uploaded_by=self.user2,
        )
        self.paper2.resource = self.res2
        self.paper2.save()

        # Both user1 and user2 save res1
        SavedResearchItem.objects.create(user=self.user1, resource=self.res1)
        SavedResearchItem.objects.create(user=self.user2, resource=self.res1)
        # user2 also saves res2 (co-occurrence)
        SavedResearchItem.objects.create(user=self.user2, resource=self.res2)

    def test_paper_recommendations_for_user(self):
        recs = RecommendationService.get_recommended_papers(self.user1, limit=5)
        self.assertIn("papers", recs)
        self.assertIn("strategy", recs)
        self.assertTrue(len(recs["papers"]) > 0)

    def test_member_recommendations(self):
        member_recs = RecommendationService.get_member_recommendations(self.user1, limit=5)
        self.assertTrue(len(member_recs) > 0)
        rec_usernames = [m["user"].username for m in member_recs]
        self.assertIn("rec_user_2", rec_usernames)

    def test_also_saved_association_rules(self):
        also_saved = RecommendationService.get_also_saved_for_paper(self.paper1, limit=5)
        self.assertTrue(len(also_saved) > 0)
        saved_titles = [item["resource"].title for item in also_saved]
        self.assertIn(self.paper2.title, saved_titles)

    def test_recommendations_home_view(self):
        self.client.force_login(self.user1)
        resp = self.client.get(reverse("recommendations:recommendations_home"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "recommendations/recommendations_home.html")
