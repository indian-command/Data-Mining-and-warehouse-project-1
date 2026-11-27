
from django.urls import path
from django.contrib.auth import views as auth_views

from . import views


app_name = "accounts"

urlpatterns = [

    path(
        "register/",
        views.register_view,
        name="register"
    ),

    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            redirect_authenticated_user=True
        ),
        name="login"
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(
            next_page="home"
        ),
        name="logout"
    ),

    path(
        "dashboard/",
        views.dashboard_view,
        name="dashboard"
    ),

    path(
        "departments/",
        views.departments_json,
        name="departments_json"
    ),
    path(
    "members/",
    views.member_list_view,
    name="members"
),

    path(
        "profile/edit/",
        views.profile_edit_view,
        name="profile_edit"
    ),
    path(
        "members/<int:user_id>/follow/",
        views.toggle_follow_view,
        name="toggle_follow"
    ),
    path(
        "members/<str:username>/",
        views.member_profile_view,
        name="member_profile"
    ),
    path(
        "profile/<str:username>/",
        views.member_profile_view,
        name="profile_detail"
    ),
    path(
        "topics/<int:topic_id>/follow/",
        views.toggle_topic_follow_view,
        name="toggle_topic_follow"
    ),
]
