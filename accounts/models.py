
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


# University schools
class School(models.Model):

    name = models.CharField(
        max_length=150,
        unique=True
    )

    code = models.CharField(
        max_length=20,
        unique=True
    )

    description = models.TextField(
        blank=True
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]

# 1. University departments
class Department(models.Model):
    school = models.ForeignKey(
    School,
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name="departments"
)

    name = models.CharField(
        max_length=150,
        unique=True
    )

    code = models.CharField(
        max_length=20,
        unique=True
    )

    description = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


# 2. Research topics
class Topic(models.Model):

    name = models.CharField(
        max_length=150,
        unique=True
    )

    description = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


# 3. Member profile
class Profile(models.Model):

    ROLE_CHOICES = [
        ("student", "Student"),
        ("faculty", "Faculty"),
        ("researcher", "Researcher"),
        ("admin", "Admin"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="student"
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members"
    )

    bio = models.TextField(
        blank=True
    )

    research_interests = models.TextField(
        blank=True
    )

    topics = models.ManyToManyField(
        Topic,
        blank=True,
        related_name="interested_members"
    )

    personal_website = models.URLField(
        blank=True
    )

    publication_url = models.URLField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"{self.user.username} - {self.role}"


# 4. Member-to-member following
class MemberFollow(models.Model):

    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="following_links"
    )

    followed = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="follower_links"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def clean(self):
        if self.follower_id == self.followed_id:
            raise ValidationError("You cannot follow yourself.")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["follower", "followed"],
                name="unique_member_follow"
            )
        ]

    def __str__(self):
        return f"{self.follower} follows {self.followed}"


# 5. Member-to-topic following
class TopicFollow(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="topic_follows"
    )

    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name="followers"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "topic"],
                name="unique_topic_follow"
            )
        ]

    def __str__(self):
        return f"{self.user} follows {self.topic}"
