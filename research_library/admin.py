from django.contrib import admin
from .models import ResearchResource


@admin.register(ResearchResource)
class ResearchResourceAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "resource_type",
        "uploaded_by",
        "created_at",
    )

    list_filter = (
        "resource_type",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
        "uploaded_by__username",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )