from django.urls import path
from unified_search import views

app_name = "unified_search"

urlpatterns = [
    path("", views.unified_search_view, name="search"),
]

