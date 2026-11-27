from django.contrib import admin
from .models import Paper, PaperCitation, PaperChunk, IngestionRunLog


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = ("title", "canonical_doi", "arxiv_id", "published_year", "pagerank_score", "save_count")
    search_fields = ("title", "canonical_doi", "arxiv_id", "abstract")
    list_filter = ("published_year", "sources")


@admin.register(PaperCitation)
class PaperCitationAdmin(admin.ModelAdmin):
    list_display = ("citing_paper", "cited_paper", "created_at")
    raw_id_fields = ("citing_paper", "cited_paper")


@admin.register(PaperChunk)
class PaperChunkAdmin(admin.ModelAdmin):
    list_display = ("paper", "chunk_index", "created_at")
    raw_id_fields = ("paper",)


@admin.register(IngestionRunLog)
class IngestionRunLogAdmin(admin.ModelAdmin):
    list_display = ("source", "status", "started_at", "completed_at", "records_fetched", "records_created", "records_updated", "watermark")
    list_filter = ("status", "source", "started_at")
    readonly_fields = ("started_at", "completed_at")

