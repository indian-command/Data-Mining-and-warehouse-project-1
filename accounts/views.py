from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from .forms import RegisterForm
from .models import Department, Profile

from .forms import RegisterForm, UserUpdateForm, ProfileUpdateForm
from .models import Department, Profile, MemberFollow

User = get_user_model()
def register_view(request):

    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if request.method == "POST":

        form = RegisterForm(request.POST)

        if form.is_valid():

            user = form.save()

            # Automatically log in the new member
            login(request, user)

            messages.success(
                request,
                "Your Research Commons account was created successfully!"
            )

            return redirect("accounts:dashboard")

    else:
        form = RegisterForm()

    return render(
        request,
        "accounts/register.html",
        {"form": form}
    )


@require_GET
def departments_json(request):

    school_id = request.GET.get("school_id")

    try:
        school_id = int(school_id)
    except (TypeError, ValueError):
        return JsonResponse([], safe=False)

    departments = Department.objects.filter(
        school_id=school_id
    ).order_by("name").values("id", "name")

    return JsonResponse(list(departments), safe=False)


@login_required
def dashboard_view(request):

    profile = Profile.objects.filter(
        user=request.user
    ).select_related(
        "department__school"
    ).prefetch_related(
        "topics"
    ).first()

    return render(
        request,
        "accounts/dashboard.html",
        {"profile": profile}
    )


@login_required
def profile_edit_view(request):

    profile = get_object_or_404(
        Profile,
        user=request.user
    )

    if request.method == "POST":

        user_form = UserUpdateForm(
            request.POST,
            instance=request.user
        )

        profile_form = ProfileUpdateForm(
            request.POST,
            instance=profile
        )

        if user_form.is_valid() and profile_form.is_valid():

            with transaction.atomic():

                user_form.save()
                profile_form.save()

            messages.success(
                request,
                "Your profile has been updated successfully!"
            )

            return redirect("accounts:dashboard")

    else:

        user_form = UserUpdateForm(
            instance=request.user
        )

        profile_form = ProfileUpdateForm(
            instance=profile
        )

    return render(
        request,
        "accounts/profile_edit.html",
        {
            "user_form": user_form,
            "profile_form": profile_form,
        }
    )

@login_required
def member_list_view(request):

    profiles = (
        Profile.objects
        .exclude(user=request.user)
        .select_related(
            "user",
            "department",
            "department__school"
        )
        .prefetch_related("topics")
        .order_by("user__first_name")
    )

    followed_ids = set(
        MemberFollow.objects.filter(
            follower=request.user
        ).values_list("followed_id", flat=True)
    )

    return render(
        request,
        "accounts/members.html",
        {
            "profiles": profiles,
            "followed_ids": followed_ids,
        }
    )


@login_required
@require_POST
def toggle_follow_view(request, user_id):

    target_user = get_object_or_404(
        User,
        pk=user_id,
        is_active=True
    )

    if target_user.pk == request.user.pk:

        messages.error(
            request,
            "You cannot follow yourself."
        )

        return redirect("accounts:members")

    follow = MemberFollow.objects.filter(
        follower=request.user,
        followed=target_user
    ).first()

    if follow:

        follow.delete()

        messages.info(
            request,
            "You have unfollowed this member."
        )

    else:

        MemberFollow.objects.get_or_create(
            follower=request.user,
            followed=target_user
        )

        messages.success(
            request,
            "You are now following this member!"
        )

    return redirect("accounts:members")
