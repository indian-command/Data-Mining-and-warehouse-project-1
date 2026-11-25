from django.urls import path
from trends import views

app_name = "trends"

urlpatterns = [
    path("", views.trends_home_view, name="trends_home"),
    path("moderation/", views.moderation_queue_view, name="moderation_queue"),
    path("moderation/<int:flag_id>/action/", views.moderation_action_view, name="moderation_action"),
]

