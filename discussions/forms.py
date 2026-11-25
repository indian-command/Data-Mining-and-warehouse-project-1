
from django import forms
from .models import DiscussionPost, Comment


class DiscussionPostForm(forms.ModelForm):

    post_type = forms.ChoiceField(
        choices=DiscussionPost.POST_TYPES,
        required=False,
        initial="discussion",
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Post Category",
    )

    class Meta:
        model = DiscussionPost

        fields = [
            "title",
            "content",
            "post_type",
            "image",
            "paper_file",
            "paper_link",
            "paper_doi",
            "tags",
            "resources",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter your research post or paper title",
                    "maxlength": 200,
                }
            ),

            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Share your research abstract, findings, discussion question, or study details...",
                    "rows": 5,
                }
            ),

            "post_type": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "image": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/*",
                }
            ),

            "paper_file": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": "application/pdf",
                }
            ),

            "paper_link": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://doi.org/... or https://arxiv.org/abs/... or Google Scholar link",
                }
            ),

            "paper_doi": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. 10.1145/3543507.3583548",
                }
            ),

            "tags": forms.CheckboxSelectMultiple(),
            "resources": forms.CheckboxSelectMultiple(),
        }

        labels = {
            "title": "Title",
            "content": "Content / Research Abstract",
            "post_type": "Post Type",
            "image": "Attach Image / Figure / Poster (Optional)",
            "paper_file": "Attach Full-Text Research Paper PDF (Optional)",
            "paper_link": "External Research Paper Link (Optional)",
            "paper_doi": "DOI Identifier (Optional)",
            "tags": "Select Research Topics",
            "resources": "Link Library Resources",
        }

        help_texts = {
            "post_type": "Select whether this is a general academic discussion, a research paper publication, or an update.",
            "image": "Supports PNG, JPG, GIF, WebP up to 10MB.",
            "paper_file": "Upload full preprint or publication PDF (up to 20MB).",
            "paper_link": "Link to external publisher, arXiv, or Google Scholar page.",
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
