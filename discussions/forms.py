
from django import forms
from .models import DiscussionPost, Comment


class DiscussionPostForm(forms.ModelForm):

    class Meta:
        model = DiscussionPost

        fields = [
            "title",
            "content",
            "tags",
            "resources",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter your research post title",
                    "resources": forms.CheckboxSelectMultiple(),
                    "maxlength": 200,
                }
            ),

            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Share your research ideas, questions or findings...",
                    "rows": 6,
                }
            ),

            "tags": forms.CheckboxSelectMultiple(),
        }

        labels = {
            "title": "Post Title",
            "content": "Your Research Content",
            "tags": "Select Research Topics",
            "resources": "Attach Research Papers or Library Links",
        }

        help_texts = {
            "tags": "Select one or more topics related to your post.",
            "resources": "Select one or more resources from the Research Library.",
        }

    def clean_title(self):
        title = self.cleaned_data["title"].strip()

        if not title:
            raise forms.ValidationError(
                "Please enter a post title."
            )

        return title

    def clean_content(self):
        content = self.cleaned_data["content"].strip()

        if not content:
            raise forms.ValidationError(
                "Post content cannot be empty."
            )

        return content


class CommentForm(forms.ModelForm):

    class Meta:
        model = Comment

        fields = ["content"]

        widgets = {
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Write your comment...",
                    "rows": 3,
                }
            )
        }

        labels = {
            "content": "Your Comment"
        }

    def clean_content(self):
        content = self.cleaned_data["content"].strip()

        if not content:
            raise forms.ValidationError(
                "Comment cannot be empty."
            )

        if len(content) > 10000:
            raise forms.ValidationError(
                "Comment cannot exceed 10,000 characters."
            )

        return content
