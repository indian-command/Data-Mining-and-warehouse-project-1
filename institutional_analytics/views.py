from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from institutional_analytics.services import DuckDBAnalyticsService, StarSchemaETLService


def analytics_dashboard_view(request):
    """Admin & Faculty Analytics Dashboard powered by DuckDB over Parquet Star Schema."""
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    if not (request.user.is_staff or (hasattr(request.user, "profile") and request.user.profile.role in ["faculty", "admin"])):
        messages.error(request, "Institutional Analytics is restricted to faculty members and administrators.")
        return redirect("home")
    dept_param = request.GET.get("dept")
    topic_param = request.GET.get("topic")

    selected_dept_id = int(dept_param) if (dept_param and dept_param.isdigit()) else None
    selected_topic_id = int(topic_param) if (topic_param and topic_param.isdigit()) else None

    # Analytical outputs from DuckDB
    dept_topics_over_time = DuckDBAnalyticsService.get_department_topics_over_time()
    collaboration_matrix = DuckDBAnalyticsService.get_cross_department_collaboration_matrix()
    most_engaged_papers = DuckDBAnalyticsService.get_most_engaged_papers()
    drill_down = DuckDBAnalyticsService.get_drill_down_stats(
        selected_dept_id=selected_dept_id, selected_topic_id=selected_topic_id
    )

    return render(
        request,
        "institutional_analytics/dashboard.html",
        {
            "dept_topics_over_time": dept_topics_over_time,
            "collaboration_matrix": collaboration_matrix,
            "most_engaged_papers": most_engaged_papers,
            "drill_down": drill_down,
            "selected_dept_id": selected_dept_id,
            "selected_topic_id": selected_topic_id,
        },
    )


@staff_member_required
@require_POST
def trigger_etl_refresh_view(request):
    """Regenerates and synchronizes Star Schema Parquet files in MinIO."""
    paths = StarSchemaETLService.run_etl()
    messages.success(request, f"Analytical Star Schema updated successfully ({len(paths)} Parquet tables generated).")
    return redirect("institutional_analytics:dashboard")
