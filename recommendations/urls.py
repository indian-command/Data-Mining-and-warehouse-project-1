from django.urls import path
from recommendations import views

app_name = "recommendations"

urlpatterns = [
    path("", views.recommendations_home_view, name="recommendations_home"),
]

