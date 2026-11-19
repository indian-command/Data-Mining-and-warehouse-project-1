
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models


class ResearchResource(models.Model):

    RESOURCE_TYPES = [
        ("paper", "Research Paper (PDF)"),
        ("link", "External Research Link"),
    ]

    title = models.CharField(
        max_length=250
    )

    description = models.TextField(
        blank=True
    )

    resource_type = models.CharField(
        max_length=20,
        choices=RESOURCE_TYPES
    )

    # Uploaded PDF paper
    file = models.FileField(
        upload_to="research_library/papers/%Y/%m/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf"]
            )
        ]
    )

    # External research link
    url = models.URLField(
        blank=True
    )
    # Digital Object Identifier
    doi = models.CharField(
    max_length=255,
    unique=True,
    null=True,
    blank=True
)

# arXiv paper identifier
    arxiv_id = models.CharField(
    max_length=100,
    unique=True,
    null=True,
    blank=True
        )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="research_resources"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def clean(self):
        super().clean()

        if self.resource_type == "paper":

            if not self.file:
                raise ValidationError({
                    "file": "Please upload a PDF research paper."
                })

            if self.file and self.file.size > 20 * 1024 * 1024:
                raise ValidationError({
                    "file": "The PDF file cannot exceed 20 MB."
                })

            if self.url:
                raise ValidationError({
                    "url": "PDF resources should not also have an external URL."
                })

        elif self.resource_type == "link":

            if not self.url:
                raise ValidationError({
                    "url": "Please provide an external research link."
                })

            if self.file:
                raise ValidationError({
                    "file": "External link resources should not have an uploaded file."
                })



    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Research Resource"
        verbose_name_plural = "Research Resources"

    def __str__(self):
        return self.title


# ==========================================
# 2. MEMBER SAVED RESEARCH ITEMS
# ==========================================

class SavedResearchItem(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_research_items"
    )

    resource = models.ForeignKey(
        ResearchResource,
        on_delete=models.CASCADE,
        related_name="saves"
    )

    private_notes = models.TextField(
        blank=True
    )

    saved_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-saved_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["user", "resource"],
                name="unique_member_saved_resource"
            )
        ]

    def __str__(self):
        return f"{self.user} saved {self.resource.title}"


# ==========================================
# 3. PERSONAL RESEARCH COLLECTIONS
# ==========================================

class ResearchCollection(models.Model):

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="research_collections"
    )

    name = models.CharField(
        max_length=150
    )

    description = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"],
                name="unique_member_collection_name"
            )
        ]

    def __str__(self):
        return f"{self.owner.username} - {self.name}"


# ==========================================
# 4. COLLECTION ITEMS
# ==========================================

class CollectionItem(models.Model):

    collection = models.ForeignKey(
        ResearchCollection,
        on_delete=models.CASCADE,
        related_name="items"
    )

    saved_item = models.ForeignKey(
        SavedResearchItem,
        on_delete=models.CASCADE,
        related_name="collection_entries"
    )

    added_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "saved_item"],
                name="unique_collection_saved_item"
            )
        ]

    def clean(self):
        super().clean()

        if (
            self.collection_id
            and self.saved_item_id
            and self.collection.owner_id != self.saved_item.user_id
        ):
            raise ValidationError(
                "You can only add your own saved items to your collections."
            )

    def __str__(self):
        return f"{self.saved_item.resource.title} in {self.collection.name}"
