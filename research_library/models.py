
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
