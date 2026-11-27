from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from trends.models import ActivityEvent, ModerationFlag, TopicTrend
from trends.services import AnomalyDetector, TrendAnalyzer


def trends_home_view(request):
    """Displays sliding-window trending topics, growth velocity, and statistical spike alerts."""
    # Ensure trends are freshly calculated or retrieved
    trends = TopicTrend.objects.select_related("topic").order_by("-is_spike", "-z_score", "-growth_rate")
    if not trends.exists():
        trends = TrendAnalyzer.calculate_topic_trends(window_days=7, baseline_days=30)

    spike_alerts = [t for t in trends if t.is_spike]
    top_trending = [t for t in trends if not t.is_spike][:12]

    recent_events = (
        ActivityEvent.objects.select_related("user")
        .exclude(event_type="search")
        .order_by("-timestamp")[:15]
    )

    return render(
        request,
        "trends/trends_home.html",
        {
            "spike_alerts": spike_alerts,
            "top_trending": top_trending,
            "recent_events": recent_events,
        },
    )


@staff_member_required
def moderation_queue_view(request):
    """Admin queue for reviewing automated anomaly detection and spam flags."""
    # Run scan on visit
    AnomalyDetector.scan_for_anomalies()

    flags = ModerationFlag.objects.select_related("user").order_by("-created_at")
    pending_flags = flags.filter(status="pending")
    resolved_flags = flags.exclude(status="pending")[:20]

    return render(
        request,
        "trends/moderation_queue.html",
        {
            "pending_flags": pending_flags,
            "resolved_flags": resolved_flags,
        },
    )


@staff_member_required
@require_POST
def moderation_action_view(request, flag_id):
    """Applies moderation resolution (dismiss, ban user)."""
    flag = get_object_or_404(ModerationFlag, pk=flag_id)
    action = request.POST.get("action")

    if action == "dismiss":
        flag.status = "dismissed"
        flag.save(update_fields=["status"])
        messages.success(request, f"Flag for {flag.user.username} was dismissed.")
    elif action == "ban":
        flag.status = "banned"
        flag.save(update_fields=["status"])
        user = flag.user
        user.is_active = False
        user.save(update_fields=["is_active"])
        messages.warning(request, f"Account {user.username} was banned and deactivated.")

    return redirect("trends:moderation_queue")
