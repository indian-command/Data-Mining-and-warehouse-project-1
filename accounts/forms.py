
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction

from .models import Profile, School, Department, Topic


User = get_user_model()


class RegisterForm(UserCreationForm):

    # Personal information
    first_name = forms.CharField(
        max_length=150,
        label="First Name"
    )

    last_name = forms.CharField(
        max_length=150,
        label="Last Name"
    )

    email = forms.EmailField(
        label="University Email"
    )

    # Academic information
    role = forms.ChoiceField(
        choices=[
            ("student", "Student"),
            ("faculty", "Faculty"),
            ("researcher", "Researcher"),
        ],
        label="Select Your Role"
    )

    school = forms.ModelChoiceField(
        queryset=School.objects.all(),
        empty_label="Select School",
        label="School"
    )

    department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        empty_label="Select Department",
        label="Department"
    )

    # Research information
    topics = forms.ModelMultipleChoiceField(
        queryset=Topic.objects.all(),
        required=False,
        label="Research Interests",
        widget=forms.SelectMultiple()
    )

    bio = forms.CharField(
        required=False,
        label="About You",
        widget=forms.Textarea(attrs={"rows": 3})
    )

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Bootstrap styling
        for name, field in self.fields.items():

            if isinstance(field.widget, forms.SelectMultiple):
                field.widget.attrs["class"] = "form-select"

            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"

            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs["class"] = "form-control"

            else:
                field.widget.attrs["class"] = "form-control"

        # Filter departments according to selected school
        school_id = self.data.get("school")

        if school_id:
            self.fields["department"].queryset = (
                Department.objects.filter(
                    school_id=school_id
                ).order_by("name")
            )

    def clean_email(self):
        email = self.cleaned_data["email"]

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "This email address is already registered."
            )

        return email

    def clean(self):
        cleaned_data = super().clean()

        school = cleaned_data.get("school")
        department = cleaned_data.get("department")

        # Ensure department belongs to selected school
        if school and department:
            if department.school_id != school.id:
                raise forms.ValidationError(
                    "Please select a department belonging to your school."
                )

        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):

        user = super().save(commit=False)

        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]

        if commit:
            user.save()

            profile = Profile.objects.create(
                user=user,
                role=self.cleaned_data["role"],
                department=self.cleaned_data["department"],
                bio=self.cleaned_data["bio"]
            )

            profile.topics.set(
                self.cleaned_data["topics"]
            )

        return user

class UserUpdateForm(forms.ModelForm):

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control"}
            ),
        }

    def clean_email(self):

        email = self.cleaned_data["email"]

        if User.objects.filter(
            email__iexact=email
        ).exclude(pk=self.instance.pk).exists():

            raise forms.ValidationError(
                "This email is already being used."
            )

        return email


class ProfileUpdateForm(forms.ModelForm):

    school = forms.ModelChoiceField(
        queryset=School.objects.all(),
        label="School",
        empty_label="Select School"
    )

    department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        label="Department",
        empty_label="Select Department"
    )

    class Meta:
        model = Profile

        fields = [
            "department",
            "bio",
            "research_interests",
            "topics",
            "personal_website",
            "publication_url",
        ]

        widgets = {
            "bio": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3
                }
            ),

            "research_interests": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3
                }
            ),

            "topics": forms.SelectMultiple(
                attrs={
                    "class": "form-select",
                    "size": 6
                }
            ),

            "personal_website": forms.URLInput(
                attrs={"class": "form-control"}
            ),

            "publication_url": forms.URLInput(
                attrs={"class": "form-control"}
            ),
        }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        # Load all university schools
        self.fields["school"].queryset = School.objects.order_by("name")

        # Select the member's existing school
        if (
            self.instance.pk
            and self.instance.department_id
            and self.instance.department.school_id
        ):
            self.initial["school"] = (
                self.instance.department.school_id
            )

        # Filter departments according to selected school
        school_id = (
            self.data.get("school")
            or self.initial.get("school")
        )

        try:
            school_id = int(school_id)

            self.fields["department"].queryset = (
                Department.objects.filter(
                    school_id=school_id
                ).order_by("name")
            )

        except (TypeError, ValueError):
            self.fields["department"].queryset = Department.objects.none()

        # Bootstrap styling for all fields
        for name, field in self.fields.items():

            if name not in ["topics"]:
                field.widget.attrs["class"] = (
                    "form-select"
                    if isinstance(field.widget, forms.Select)
                    else "form-control"
                )

    def clean(self):

        cleaned_data = super().clean()

        school = cleaned_data.get("school")
        department = cleaned_data.get("department")

        if school and department:
            if department.school_id != school.id:
                self.add_error(
                    "department",
                    "Select a department belonging to the selected school."
                )

        return cleaned_data
