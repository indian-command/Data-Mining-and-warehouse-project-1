
from django.contrib import admin

from .models import (
    ResearchResource,
    SavedResearchItem,
    ResearchCollection,
    CollectionItem,
)


@admin.register(ResearchResource)
class ResearchResourceAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "resource_type",
        "doi",
        "arxiv_id",
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
        "doi",
        "arxiv_id",
        "uploaded_by__username",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(SavedResearchItem)
class SavedResearchItemAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "resource",
        "saved_at",
    )

    list_filter = (
        "saved_at",
    )

    search_fields = (
        "user__username",
        "resource__title",
        "resource__doi",
        "resource__arxiv_id",
    )

    readonly_fields = (
        "saved_at",
    )


@admin.register(ResearchCollection)
class ResearchCollectionAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "owner",
        "created_at",
    )

    search_fields = (
        "name",
        "owner__username",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(CollectionItem)
class CollectionItemAdmin(admin.ModelAdmin):

    list_display = (
        "collection",
        "saved_item",
        "added_at",
    )

    readonly_fields = (
        "added_at",
    )
