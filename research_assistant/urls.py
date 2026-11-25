from django.urls import path
from research_assistant import views

app_name = "research_assistant"

urlpatterns = [
    path("", views.assistant_view, name="assistant"),
]

