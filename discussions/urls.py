
from django.urls import path
from . import views

app_name = "discussions"

urlpatterns = [
    path("", views.post_list_view, name="post_list"),

    path("create/", views.post_create_view, name="post_create"),

    path("edit/<int:post_id>/", views.post_edit_view, name="post_edit"),

    path("delete/<int:post_id>/", views.post_delete_view, name="post_delete"),

    path("upvote/<int:post_id>/", views.toggle_upvote_view, name="toggle_upvote"),

    path("comment/<int:post_id>/",views.comment_create_view,name="comment_create"),
]
