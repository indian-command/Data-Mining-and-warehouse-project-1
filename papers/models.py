from django.db import models
from pgvector.django import VectorField


class Paper(models.Model):
    """Scholarly publication ingested from external sources or linked to research library."""
    canonical_doi = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )
    arxiv_id = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )
    openalex_id = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )
    title = models.TextField()
    authors = models.JSONField(default=list, blank=True)
    abstract = models.TextField(blank=True, default="")
    published_year = models.IntegerField(null=True, blank=True, db_index=True)
    venue = models.CharField(max_length=255, blank=True, default="")
    url = models.URLField(max_length=500, blank=True, default="")
    sources = models.JSONField(default=list, blank=True)  # e.g. ["openalex", "arxiv", "library"]
    pagerank_score = models.FloatField(default=0.0, db_index=True)
    save_count = models.IntegerField(default=0)
    citation_count = models.IntegerField(default=0)
    embedding = VectorField(dimensions=384, null=True, blank=True)

    # Link with research_library.ResearchResource cleanly
    resource = models.ForeignKey(
        "research_library.ResearchResource",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="papers",
    )
    topics = models.ManyToManyField(
        "accounts.Topic",
        blank=True,
        related_name="papers",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-pagerank_score", "-published_year", "-created_at"]
        indexes = [
            models.Index(fields=["published_year"]),
            models.Index(fields=["pagerank_score"]),
        ]

    def __str__(self):
        return self.title[:80]

    @property
    def authors_display(self):
        if not self.authors:
            return "Unknown Authors"
        if isinstance(self.authors, list):
            return ", ".join(self.authors[:5]) + (" et al." if len(self.authors) > 5 else "")
        return str(self.authors)

    @property
    def google_scholar_url(self):
        """Direct search & view URL on Google Scholar."""
        import urllib.parse
        return f"https://scholar.google.com/scholar?q={urllib.parse.quote(self.title)}"

    @property
    def google_search_url(self):
        """Direct search URL on Google Web."""
        import urllib.parse
        return f"https://www.google.com/search?q={urllib.parse.quote(self.title + ' research paper')}"

    @property
    def google_viewer_url(self):
        """Online viewer link through Google Docs Viewer or Google Scholar fallback."""
        import urllib.parse
        if self.url:
            return f"https://docs.google.com/viewer?url={urllib.parse.quote(self.url)}"
        return self.google_scholar_url

    @property
    def google_url(self):
        return self.google_scholar_url


class PaperCitation(models.Model):
    """Citation graph edge between two papers."""
    citing_paper = models.ForeignKey(
        Paper,
        on_delete=models.CASCADE,
        related_name="citations_made",
    )
    cited_paper = models.ForeignKey(
        Paper,
        on_delete=models.CASCADE,
        related_name="citations_received",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["citing_paper", "cited_paper"],
                name="unique_paper_citation",
            )
        ]
        indexes = [
            models.Index(fields=["citing_paper"]),
            models.Index(fields=["cited_paper"]),
        ]

    def __str__(self):
        return f"{self.citing_paper_id} -> {self.cited_paper_id}"


class PaperChunk(models.Model):
    """Text chunk of a paper for RAG retrieval in F8."""
    paper = models.ForeignKey(
        Paper,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    chunk_index = models.IntegerField()
    chunk_text = models.TextField()
    embedding = VectorField(dimensions=384, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["paper", "chunk_index"]
        indexes = [
            models.Index(fields=["paper", "chunk_index"]),
        ]

    def __str__(self):
        return f"Paper {self.paper_id} - Chunk {self.chunk_index}"


class IngestionRunLog(models.Model):
    """Tracks scheduled batch ingestion runs, status, incremental watermarks, and error logs."""
    source = models.CharField(max_length=50, default="scheduled_batch")  # openalex, arxiv, rss, all
    status = models.CharField(max_length=20, default="pending")  # pending, running, success, failed, partial
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    records_fetched = models.IntegerField(default=0)
    records_created = models.IntegerField(default=0)
    records_updated = models.IntegerField(default=0)
    watermark = models.CharField(max_length=255, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"[{self.source}] {self.status} at {self.started_at.strftime('%Y-%m-%d %H:%M')}"
