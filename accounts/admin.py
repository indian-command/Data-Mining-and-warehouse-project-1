
from django.contrib import admin

from .models import (
    School,
    Department,
    Topic,
    Profile,
    MemberFollow,
    TopicFollow
)



@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):

    list_display = ("name", "code")
    search_fields = ("name", "code")

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):

    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "role",
        "department",
        "created_at"
    )

    list_filter = ("role", "department")
    search_fields = ("user__username", "user__email")
    filter_horizontal = ("topics",)


@admin.register(MemberFollow)
class MemberFollowAdmin(admin.ModelAdmin):

    list_display = ("follower", "followed", "created_at")
    search_fields = ("follower__username", "followed__username")


@admin.register(TopicFollow)
class TopicFollowAdmin(admin.ModelAdmin):

    list_display = ("user", "topic", "created_at")
    search_fields = ("user__username", "topic__name")

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):

    list_display = ("name", "code", "school")

    list_filter = ("school",)

    search_fields = ("name", "code", "school__name")