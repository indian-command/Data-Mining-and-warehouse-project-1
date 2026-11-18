
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


# ==========================================
# 1. RESEARCH DISCUSSION POST
# ==========================================

class DiscussionPost(models.Model):

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="discussion_posts"
    )

    title = models.CharField(max_length=200)

    content = models.TextField()

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
        ]

    def __str__(self):
        return self.title

    @property
    def upvote_count(self):
        return self.votes.count()

    @property
    def comment_count(self):
        return self.comments.count()


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
