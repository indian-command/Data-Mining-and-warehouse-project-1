import math
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import Topic
from discussions.models import DiscussionPost
from trends.models import ActivityEvent, ModerationFlag, TopicTrend

User = get_user_model()


class EventLogger:
    """Central event logging for user interactions across the Commons."""

    @staticmethod
    def log_event(
        user: Optional[Any],
        event_type: str,
        target_type: str = "",
        target_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[ActivityEvent]:
        try:
            return ActivityEvent.objects.create(
                user=user if getattr(user, "is_authenticated", False) else None,
                event_type=event_type,
                target_type=target_type,
                target_id=str(target_id),
                metadata=metadata or {},
                timestamp=timezone.now(),
            )
        except Exception:
            return None


class TrendAnalyzer:
    """Sliding-window trending topic velocity and statistical spike detection."""

    @classmethod
    def calculate_topic_trends(cls, window_days: int = 7, baseline_days: int = 30) -> List[TopicTrend]:
        now = timezone.now()
        recent_cutoff = now - timedelta(days=window_days)
        baseline_cutoff = now - timedelta(days=baseline_days)

        all_topics = Topic.objects.all()
        trends_to_save = []

        for topic in all_topics:
            # 1. Count discussion posts tagged with this topic in recent window
            recent_post_count = DiscussionPost.objects.filter(
                tags=topic, created_at__gte=recent_cutoff
            ).count()

            # Count activity events mentioning this topic
            recent_event_count = ActivityEvent.objects.filter(
                metadata__topic=topic.name, timestamp__gte=recent_cutoff
            ).count()

            current_count = recent_post_count + recent_event_count

            # 2. Historical slices over baseline to compute mean and std dev
            slice_days = window_days
            num_slices = max(1, baseline_days // slice_days)
            slice_counts = []

            # 2. Historical slices over baseline strictly PRIOR to recent window
            slice_days = window_days
            num_slices = max(1, baseline_days // slice_days)
            slice_counts = []

            for i in range(1, num_slices + 1):
                start = now - timedelta(days=window_days + (i * slice_days))
                end = now - timedelta(days=window_days + ((i - 1) * slice_days))
                posts = DiscussionPost.objects.filter(
                    tags=topic, created_at__gte=start, created_at__lt=end
                ).count()
                events = ActivityEvent.objects.filter(
                    metadata__topic=topic.name, timestamp__gte=start, timestamp__lt=end
                ).count()
                slice_counts.append(posts + events)

            mean_baseline = sum(slice_counts) / len(slice_counts) if slice_counts else 0.0
            variance = (
                sum((x - mean_baseline) ** 2 for x in slice_counts) / len(slice_counts)
                if slice_counts
                else 0.0
            )
            std_dev = math.sqrt(variance)

            # Z-Score computation
            if std_dev > 0.05:
                z_score = (current_count - mean_baseline) / std_dev
            else:
                z_score = float(current_count - mean_baseline)

            # Growth rate percentage
            if mean_baseline > 0:
                growth_rate = ((current_count - mean_baseline) / mean_baseline) * 100.0
            else:
                growth_rate = float(current_count * 100.0)

            # Spike alert condition: z-score >= 2.0 or >=2x baseline with minimum activity
            is_spike = bool((z_score >= 2.0 or (mean_baseline > 0 and current_count >= mean_baseline * 2.0)) and current_count >= 10)

            trend_record, _ = TopicTrend.objects.update_or_create(
                topic=topic,
                defaults={
                    "window_days": window_days,
                    "current_count": current_count,
                    "baseline_count": round(mean_baseline, 2),
                    "growth_rate": round(growth_rate, 2),
                    "z_score": round(z_score, 2),
                    "is_spike": is_spike,
                },
            )
            trends_to_save.append(trend_record)

        return sorted(trends_to_save, key=lambda t: (t.is_spike, t.z_score), reverse=True)


class AnomalyDetector:
    """Detects suspicious spam accounts, abnormal burst activity, and duplicate floods."""

    @classmethod
    def scan_for_anomalies(cls) -> List[ModerationFlag]:
        flags_created = []
        now = timezone.now()
        two_hours_ago = now - timedelta(hours=2)

        users = User.objects.filter(is_active=True).exclude(is_staff=True)

        for user in users:
            # 1. Burst posting detection (>5 posts in recent window)
            recent_posts = DiscussionPost.objects.filter(
                author=user, created_at__gte=two_hours_ago
            )
            if recent_posts.count() >= 5:
                flag, _ = ModerationFlag.objects.get_or_create(
                    user=user,
                    flag_reason="Abnormal burst posting (>5 posts in recent window)",
                    status="pending",
                    defaults={
                        "severity": "high",
                        "details": {
                            "post_count": recent_posts.count(),
                            "time_window": "2h",
                            "sample_titles": list(recent_posts.values_list("title", flat=True)[:3]),
                        },
                    },
                )
                flags_created.append(flag)

            # 2. Identical duplicate content flood
            titles = list(
                DiscussionPost.objects.filter(author=user, created_at__gte=two_hours_ago).values_list(
                    "title", flat=True
                )
            )
            if len(titles) >= 3 and len(set(titles)) == 1:
                flag, _ = ModerationFlag.objects.get_or_create(
                    user=user,
                    flag_reason="Repeated identical posts (potential automated spam)",
                    status="pending",
                    defaults={
                        "severity": "high",
                        "details": {"identical_title": titles[0], "count": len(titles)},
                    },
                )
                flags_created.append(flag)

            # 3. Burst rapid saving/activity (>30 events in 5 minutes)
            five_mins_ago = now - timedelta(minutes=5)
            burst_events = ActivityEvent.objects.filter(user=user, timestamp__gte=five_mins_ago).count()
            if burst_events >= 30:
                flag, _ = ModerationFlag.objects.get_or_create(
                    user=user,
                    flag_reason="Unusual high-frequency bot-like activity (>30 actions in 5m)",
                    status="pending",
                    defaults={
                        "severity": "medium",
                        "details": {"event_count": burst_events, "time_window": "5m"},
                    },
                )
                flags_created.append(flag)

        return flags_created
