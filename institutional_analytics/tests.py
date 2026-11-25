from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from accounts.models import Department, School, Topic, Profile
from papers.models import Paper
from trends.models import ActivityEvent
from institutional_analytics.services import StarSchemaETLService, DuckDBAnalyticsService

User = get_user_model()


class InstitutionalAnalyticsTests(TestCase):

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="dean_analytics", email="dean@chanakya.edu.in", password="Pass123!", is_staff=True
        )
        self.school = School.objects.create(name="School of Computing", code="SC")
        self.dept = Department.objects.create(name="Computer Science & AI", code="CSAI", school=self.school)
        self.topic = Topic.objects.create(name="Machine Learning")
        self.profile = Profile.objects.create(user=self.staff_user, department=self.dept, role="faculty")

        self.paper = Paper.objects.create(
            title="Statistical Learning Foundations",
            canonical_doi="10.1145/stat.1",
            published_year=2023,
            save_count=4,
            pagerank_score=0.08,
        )

        ActivityEvent.objects.create(
            user=self.staff_user,
            event_type="view_paper",
            target_type="paper",
            target_id=str(self.paper.id),
            metadata={"topic_id": self.topic.id, "topic": "Machine Learning"},
        )

    def test_star_schema_etl_generates_parquet_files(self):
        paths = StarSchemaETLService.run_etl()
        self.assertIn("dim_department", paths)
        self.assertIn("dim_user", paths)
        self.assertIn("dim_topic", paths)
        self.assertIn("dim_time", paths)
        self.assertIn("fact_activity", paths)

    def test_duckdb_queries(self):
        # 1. Topics over time
        topics_time = DuckDBAnalyticsService.get_department_topics_over_time()
        self.assertIsInstance(topics_time, list)

        # 2. Most engaged papers
        engaged = DuckDBAnalyticsService.get_most_engaged_papers()
        self.assertTrue(len(engaged) > 0)
        self.assertEqual(engaged[0]["id"], self.paper.id)

        # 3. Drill down stats
        drill = DuckDBAnalyticsService.get_drill_down_stats(selected_dept_id=self.dept.id)
        self.assertIn("university", drill)
        self.assertIn("departments", drill)
        self.assertIn("topics", drill)

    def test_analytics_dashboard_view_permissions(self):
        # Regular user denied
        reg_user = User.objects.create_user(username="student_x", password="Pass123!")
        self.client.force_login(reg_user)
        resp = self.client.get(reverse("institutional_analytics:dashboard"))
        self.assertEqual(resp.status_code, 302)

        # Staff user allowed
        self.client.force_login(self.staff_user)
        resp = self.client.get(reverse("institutional_analytics:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "institutional_analytics/dashboard.html")
