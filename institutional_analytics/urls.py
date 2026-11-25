from django.urls import path
from institutional_analytics import views

app_name = "institutional_analytics"

urlpatterns = [
    path("", views.analytics_dashboard_view, name="dashboard"),
    path("refresh/", views.trigger_etl_refresh_view, name="refresh_etl"),
]

