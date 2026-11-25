from django.urls import path
from papers import views

app_name = "papers"

urlpatterns = [
    path("", views.paper_list_view, name="paper_list"),
    path("<int:pk>/", views.paper_detail_view, name="paper_detail"),
    path("<int:pk>/save/", views.save_paper_to_library_view, name="save_paper"),
]

