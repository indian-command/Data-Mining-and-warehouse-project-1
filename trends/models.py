from django.conf import settings
from django.db import models
from django.utils import timezone


class ActivityEvent(models.Model):
    """Event log capturing user interactions for DuckDB Parquet ETL and Trends."""
    EVENT_TYPES = [
        ("search", "Search"),
        ("view_paper", "View Paper"),
        ("save_paper", "Save Paper"),
        ("create_post", "Create Post"),
        ("comment", "Comment"),
        ("upvote", "Upvote"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_events",
    )
    event_type = models.CharField(max_length=40, choices=EVENT_TYPES, db_index=True)
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["-timestamp"]),
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["event_type", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.event_type} at {self.timestamp}"


class TopicTrend(models.Model):
    """Calculated sliding-window velocity and spike anomaly metrics for research topics."""
    topic = models.ForeignKey(
        "accounts.Topic",
        on_delete=models.CASCADE,
        related_name="trend_records",
    )
    window_days = models.IntegerField(default=7)
    current_count = models.IntegerField(default=0)
    baseline_count = models.FloatField(default=0.0)
    growth_rate = models.FloatField(default=0.0)
    z_score = models.FloatField(default=0.0)
    is_spike = models.BooleanField(default=False, db_index=True)
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_spike", "-z_score", "-growth_rate"]

    def __str__(self):
        return f"{self.topic.name} (Z={self.z_score:.2f}, spike={self.is_spike})"


class ModerationFlag(models.Model):
    """Suspicious account or burst activity alert flagged for Admin Moderation Queue."""
    SEVERITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending Review"),
        ("dismissed", "Dismissed"),
        ("banned", "Account Banned"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="moderation_flags",
    )
    flag_reason = models.CharField(max_length=255)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="medium")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Flag: {self.user.username} - {self.flag_reason} [{self.status}]"
