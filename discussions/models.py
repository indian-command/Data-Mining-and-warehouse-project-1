
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models


# ==========================================
# 1. RESEARCH DISCUSSION POST
# ==========================================

class DiscussionPost(models.Model):

    POST_TYPES = [
        ("discussion", "Scholarly Discussion"),
        ("paper", "Research Paper Publication"),
        ("update", "Research Update / Announcement"),
    ]

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="discussion_posts"
    )

    title = models.CharField(max_length=200)

    content = models.TextField()

    post_type = models.CharField(
        max_length=20,
        choices=POST_TYPES,
        default="discussion",
        blank=True,
        db_index=True,
    )

    # Optional image attachment (figures, diagrams, posters, graphs)
    image = models.ImageField(
        upload_to="discussions/images/%Y/%m/",
        blank=True,
        null=True,
        help_text="Attach a research diagram, chart, experimental figure or poster",
    )

    # Optional direct PDF research paper attachment
    paper_file = models.FileField(
        upload_to="discussions/papers/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf"])],
        help_text="Attach full-text research paper (PDF)",
    )

    # Optional external paper link (Google Scholar, arXiv, DOI, publisher)
    paper_link = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="External link to Google Scholar, arXiv, DOI, or publication website",
    )

    # Optional canonical DOI
    paper_doi = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Canonical DOI identifier (e.g. 10.1145/...)",
    )

    # Research topic tags
    tags = models.ManyToManyField(
        "accounts.Topic",
        blank=True,
        related_name="discussion_posts"
    )

    # Research papers and library links
    resources = models.ManyToManyField(
        "research_library.ResearchResource",
        blank=True,
        related_name="discussion_posts"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["-created_at"],
                name="discussion_created_idx"
            ),
            models.Index(
                fields=["author", "-created_at"],
                name="discussion_author_idx"
            ),
            models.Index(
                fields=["post_type", "-created_at"],
                name="discussion_type_created_idx"
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def upvote_count(self):
        return self.votes.count()

    @property
    def comment_count(self):
        return self.comments.count()

    @property
    def save_count(self):
        return self.saved_by_users.count()

    @property
    def is_paper(self):
        return self.post_type == "paper" or bool(self.paper_file) or bool(self.paper_link)


# ==========================================
# 2. COMMENTS AND REPLIES
# ==========================================

class Comment(models.Model):

    post = models.ForeignKey(
        DiscussionPost,
        on_delete=models.CASCADE,
        related_name="comments"
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="discussion_comments"
    )

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies"
    )

    content = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["created_at"]

        indexes = [
            models.Index(
                fields=["post", "created_at"],
                name="comment_post_created_idx"
            )
        ]

    def clean(self):
        super().clean()

        if self.parent_id:

            if self.parent.post_id != self.post_id:
                raise ValidationError(
                    "A reply must belong to the same post as its parent comment."
                )

            if self.parent.parent_id:
                raise ValidationError(
                    "Replies can only be made to top-level comments."
                )

    def __str__(self):
        return f"Comment by {self.author} on {self.post.title}"


# ==========================================
# 3. POST UPVOTES
# ==========================================

class PostVote(models.Model):

    post = models.ForeignKey(
        DiscussionPost,
        on_delete=models.CASCADE,
        related_name="votes"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="discussion_votes"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["post", "user"],
                name="unique_user_post_upvote"
            )
        ]

        indexes = [
            models.Index(
                fields=["post", "created_at"],
                name="postvote_post_created_idx"
            )
        ]

    def __str__(self):
        return f"{self.user} upvoted {self.post.title}"


# ==========================================
# 4. SAVED POSTS (BOOKMARKS)
# ==========================================

class SavedPost(models.Model):

    post = models.ForeignKey(
        DiscussionPost,
        on_delete=models.CASCADE,
        related_name="saved_by_users"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_discussion_posts"
    )

    saved_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-saved_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["post", "user"],
                name="unique_user_saved_discussion_post"
            )
        ]

        indexes = [
            models.Index(
                fields=["user", "-saved_at"],
                name="savedpost_user_saved_idx"
            ),
            models.Index(
                fields=["post", "saved_at"],
                name="savedpost_post_saved_idx"
            ),
        ]

    def __str__(self):
        return f"{self.user} saved {self.post.title}"

