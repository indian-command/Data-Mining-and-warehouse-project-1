from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from accounts.models import Topic
from discussions.models import DiscussionPost
from trends.models import ActivityEvent, ModerationFlag, TopicTrend
from trends.services import EventLogger, TrendAnalyzer, AnomalyDetector

User = get_user_model()


class TrendsAndAnomalyTests(TestCase):

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff_mod", email="mod@example.com", password="Pass123!", is_staff=True
        )
        self.regular_user = User.objects.create_user(
            username="student_mod", email="stud@example.com", password="Pass123!"
        )
        self.topic = Topic.objects.create(name="Quantum Computing")

    def test_event_logger(self):
        ev = EventLogger.log_event(
            user=self.regular_user,
            event_type="search",
            target_type="query",
            target_id="Quantum Qubits",
            metadata={"topic": "Quantum Computing"},
        )
        self.assertIsNotNone(ev)
        self.assertEqual(ev.event_type, "search")
        self.assertEqual(ev.user, self.regular_user)

    def test_trend_analyzer_and_spike_detection(self):
        now = timezone.now()
        # Seed sudden surge of activity events
        for _ in range(8):
            ActivityEvent.objects.create(
                user=self.regular_user,
                event_type="search",
                target_type="topic",
                target_id="Quantum Computing",
                metadata={"topic": "Quantum Computing", "topic_id": self.topic.id},
                timestamp=now - timedelta(days=1),
            )

        trends = TrendAnalyzer.calculate_topic_trends(window_days=7, baseline_days=30)
        self.assertTrue(len(trends) > 0)
        q_trend = next((t for t in trends if t.topic.id == self.topic.id), None)
        self.assertIsNotNone(q_trend)
        self.assertGreaterEqual(q_trend.current_count, 8)

    def test_anomaly_detector_burst_posting(self):
        now = timezone.now()
        # Create 6 burst posts in 3 minutes
        for i in range(6):
            DiscussionPost.objects.create(
                author=self.regular_user,
                title=f"Spam Post {i}",
                content=f"Commercial promotion content #{i}",
                created_at=now - timedelta(minutes=i),
            )

        flags = AnomalyDetector.scan_for_anomalies()
        self.assertTrue(len(flags) > 0)
        flagged_users = [f.user.id for f in flags]
        self.assertIn(self.regular_user.id, flagged_users)

    def test_trends_home_view(self):
        resp = self.client.get(reverse("trends:trends_home"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "trends/trends_home.html")

    def test_moderation_queue_permissions(self):
        # Anonymous / regular user redirected
        resp = self.client.get(reverse("trends:moderation_queue"))
        self.assertEqual(resp.status_code, 302)

        # Staff user allowed
        self.client.force_login(self.staff_user)
        resp = self.client.get(reverse("trends:moderation_queue"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "trends/moderation_queue.html")
