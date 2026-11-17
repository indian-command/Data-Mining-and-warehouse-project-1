
from django.contrib import admin

from .models import DiscussionPost, Comment, PostVote


@admin.register(DiscussionPost)
class DiscussionPostAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "author",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "title",
        "content",
        "author__username",
    )

    list_filter = ("created_at",)

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    date_hierarchy = "created_at"


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):

    list_display = (
        "post",
        "author",
        "parent",
        "created_at",
    )

    search_fields = (
        "content",
        "author__username",
        "post__title",
    )

    list_filter = ("created_at",)


@admin.register(PostVote)
class PostVoteAdmin(admin.ModelAdmin):

    list_display = (
        "post",
        "user",
        "created_at",
    )

    search_fields = (
        "post__title",
        "user__username",
    )

    list_filter = ("created_at",)
