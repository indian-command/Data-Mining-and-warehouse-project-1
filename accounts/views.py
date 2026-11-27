from functools import wraps
from django.contrib import messages
from django.contrib.auth import login, get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from .forms import RegisterForm, UserUpdateForm, ProfileUpdateForm
from .models import (
    Department,
    Profile,
    MemberFollow,
    School,
    Topic,
    TopicFollow,
)

User = get_user_model()

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
    from django.db.models import Count, Q
    from .models import School

    query = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "").strip()
    school_filter = request.GET.get("school", "").strip()
    following_only = request.GET.get("following", "").strip()

    profiles = (
        Profile.objects
        .exclude(user=request.user)
        .select_related(
            "user",
            "department",
            "department__school"
        )
        .prefetch_related("topics")
        .annotate(
            posts_count=Count("user__discussion_posts", distinct=True),
            followers_count=Count("user__follower_links", distinct=True),
            following_count=Count("user__following_links", distinct=True),
        )
    )

    if query:
        profiles = profiles.filter(
            Q(user__username__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(department__name__icontains=query) |
            Q(department__school__name__icontains=query) |
            Q(bio__icontains=query) |
            Q(topics__name__icontains=query)
        ).distinct()

    if role_filter:
        profiles = profiles.filter(role=role_filter)

    if school_filter:
        profiles = profiles.filter(department__school__code=school_filter)

    followed_ids = set(
        MemberFollow.objects.filter(
            follower=request.user
        ).values_list("followed_id", flat=True)
    )

    if following_only == "1":
        profiles = profiles.filter(user_id__in=followed_ids)

    profiles = profiles.order_by("-followers_count", "user__first_name")

    # Current user's Instagram-style profile stats
    my_profile = getattr(request.user, "profile", None)
    my_posts_count = request.user.discussion_posts.count()
    my_followers_count = request.user.follower_links.count()
    my_following_count = request.user.following_links.count()

    schools = School.objects.all().order_by("name")

    return render(
        request,
        "accounts/members.html",
        {
            "profiles": profiles,
            "followed_ids": followed_ids,
            "my_profile": my_profile,
            "my_posts_count": my_posts_count,
            "my_followers_count": my_followers_count,
            "my_following_count": my_following_count,
            "query": query,
            "role_filter": role_filter,
            "school_filter": school_filter,
            "schools": schools,
            "following_only": following_only,
            "total_researchers": profiles.count(),
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
            f"You have unfollowed @{target_user.username}."
        )

    else:

        MemberFollow.objects.get_or_create(
            follower=request.user,
            followed=target_user
        )

        messages.success(
            request,
            f"You are now following @{target_user.username}!"
        )

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
    if next_url:
        return redirect(next_url)

    return redirect("accounts:members")


# =====================================
# INDIVIDUAL MEMBER PROFILE VIEW
# =====================================

def member_profile_view(request, username):
    """
    Public academic profile page for an individual university researcher/student.
    Displays user metadata, role, department, bio, topics, followers, following,
    and all discussion posts authored by the member.
    """
    target_user = User.objects.select_related(
        "profile",
        "profile__department",
        "profile__department__school"
    ).prefetch_related("profile__topics").filter(username=username).first()

    # Graceful redirection for legacy member_X handles
    if not target_user and username.startswith("member_"):
        try:
            m_num = int(username.replace("member_", ""))
            cand_user = User.objects.filter(id=m_num + 1).first() or User.objects.filter(id=m_num).first()
            if cand_user:
                return redirect("accounts:member_profile", username=cand_user.username)
        except ValueError:
            pass

    if not target_user:
        target_user = get_object_or_404(
            User.objects.select_related(
                "profile",
                "profile__department",
                "profile__department__school"
            ).prefetch_related("profile__topics"),
            username=username
        )

    target_profile = getattr(target_user, "profile", None)

    posts = (
        target_user.discussion_posts
        .select_related("author", "author__profile")
        .prefetch_related("tags", "comments", "votes")
        .order_by("-created_at")
    )
    posts_count = posts.count()

    followers_qs = (
        MemberFollow.objects
        .filter(followed=target_user)
        .select_related("follower", "follower__profile", "follower__profile__department")
    )
    followers_count = followers_qs.count()

    following_qs = (
        MemberFollow.objects
        .filter(follower=target_user)
        .select_related("followed", "followed__profile", "followed__profile__department")
    )
    following_count = following_qs.count()

    is_following = False
    if request.user.is_authenticated and request.user != target_user:
        is_following = MemberFollow.objects.filter(
            follower=request.user,
            followed=target_user
        ).exists()

    my_followed_ids = set()
    if request.user.is_authenticated:
        my_followed_ids = set(
            MemberFollow.objects.filter(
                follower=request.user
            ).values_list("followed_id", flat=True)
        )

    context = {
        "target_user": target_user,
        "target_profile": target_profile,
        "posts": posts,
        "posts_count": posts_count,
        "followers": followers_qs,
        "followers_count": followers_count,
        "following": following_qs,
        "following_count": following_count,
        "is_following": is_following,
        "is_self": (request.user == target_user),
        "my_followed_ids": my_followed_ids,
    }
    return render(request, "accounts/member_profile.html", context)

# =====================================
# FOLLOW / UNFOLLOW RESEARCH TOPICS
# =====================================

@login_required
@require_POST
def toggle_topic_follow_view(request, topic_id):

    topic = get_object_or_404(
        Topic,
        pk=topic_id
    )

    follow = TopicFollow.objects.filter(
        user=request.user,
        topic=topic
    ).first()

    if follow:
        follow.delete()

        messages.info(
            request,
            f"You unfollowed {topic.name}."
        )

    else:
        TopicFollow.objects.get_or_create(
            user=request.user,
            topic=topic
        )

        messages.success(
            request,
            f"You are now following {topic.name}!"
        )

    return redirect("discussions:post_list")


# =====================================
# ADMIN USER DIRECTORY & ACCESS CONTROL
# =====================================

def _admin_required(view_func):
    """Allows staff/superuser/admin-role accounts; redirects guests and returns 403 for non-admins."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        profile = getattr(request.user, "profile", None)
        is_admin = (
            request.user.is_staff
            or request.user.is_superuser
            or (profile is not None and profile.role == "admin")
        )
        if not is_admin:
            return HttpResponseForbidden("403 Forbidden: Administrator access required.")
        return view_func(request, *args, **kwargs)
    return _wrapped


@_admin_required
def admin_user_directory_view(request):
    """Admin-only User Directory & Access Control Console."""
    query = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "").strip()
    school_filter = request.GET.get("school", "").strip()
    status_filter = request.GET.get("status", "").strip()

    all_users = User.objects.select_related(
        "profile", "profile__department", "profile__department__school"
    ).order_by("-is_active", "first_name", "username")

    # KPI Summary metrics (university-wide)
    total_accounts = User.objects.count()
    active_count = User.objects.filter(is_active=True).count()
    suspended_count = User.objects.filter(is_active=False).count()
    faculty_count = Profile.objects.filter(role="faculty").count()
    student_count = Profile.objects.filter(role="student").count()
    researcher_count = Profile.objects.filter(role="researcher").count()
    admin_count = Profile.objects.filter(role="admin").count()
    schools = School.objects.all().order_by("name")
    schools_count = schools.count() or 6

    # Apply filters
    users_qs = all_users
    if query:
        users_qs = users_qs.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(profile__department__name__icontains=query)
            | Q(profile__department__school__name__icontains=query)
        ).distinct()

    if role_filter:
        users_qs = users_qs.filter(profile__role=role_filter)

    if school_filter:
        users_qs = users_qs.filter(profile__department__school__code=school_filter)

    if status_filter == "active":
        users_qs = users_qs.filter(is_active=True)
    elif status_filter == "suspended":
        users_qs = users_qs.filter(is_active=False)

    return render(
        request,
        "accounts/admin_users.html",
        {
            "users_list": users_qs,
            "filtered_count": users_qs.count(),
            "total_accounts": total_accounts,
            "active_count": active_count,
            "suspended_count": suspended_count,
            "faculty_count": faculty_count,
            "student_count": student_count,
            "researcher_count": researcher_count,
            "admin_count": admin_count,
            "schools": schools,
            "schools_count": schools_count,
            "role_choices": Profile.ROLE_CHOICES,
            "query": query,
            "role_filter": role_filter,
            "school_filter": school_filter,
            "status_filter": status_filter,
        },
    )


@_admin_required
@require_POST
def admin_update_role_view(request, user_id):
    """Updates a scholar's academic role track via POST."""
    target_user = get_object_or_404(User, pk=user_id)
    new_role = request.POST.get("role", "").strip()
    valid_roles = {r[0] for r in Profile.ROLE_CHOICES}
    if new_role not in valid_roles:
        messages.error(request, "Invalid role selection.")
        return redirect("accounts:admin_users")

    profile, _ = Profile.objects.get_or_create(user=target_user)
    profile.role = new_role
    profile.save(update_fields=["role"])

    if new_role == "admin" and not target_user.is_staff:
        target_user.is_staff = True
        target_user.save(update_fields=["is_staff"])

    messages.success(request, f"Updated role for {target_user.username} to {profile.get_role_display()}.")
    return redirect("accounts:admin_users")


@_admin_required
@require_POST
def admin_toggle_status_view(request, user_id):
    """Suspends or reactivates a user account (self-suspension blocked)."""
    target_user = get_object_or_404(User, pk=user_id)
    if target_user.pk == request.user.pk:
        messages.error(request, "You cannot suspend your own logged-in administrator account.")
        return redirect("accounts:admin_users")

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=["is_active"])
    state_label = "reactivated" if target_user.is_active else "suspended"
    messages.success(request, f"Account {target_user.username} has been {state_label}.")
    return redirect("accounts:admin_users")


@_admin_required
@require_POST
def admin_toggle_verify_view(request, user_id):
    """Toggles a scholar's verification status between Verified and Pending."""
    target_user = get_object_or_404(User, pk=user_id)
    profile, _ = Profile.objects.get_or_create(user=target_user)
    profile.is_verified = not profile.is_verified
    profile.save(update_fields=["is_verified"])
    status_label = "Verified" if profile.is_verified else "Pending"
    messages.success(request, f"Verification status for {target_user.username} set to {status_label}.")
    return redirect("accounts:admin_users")


@_admin_required
@require_POST
def admin_reset_password_view(request, user_id):
    """Sets a temporary password for a user account."""
    target_user = get_object_or_404(User, pk=user_id)
    temp_password = request.POST.get("temp_password", "").strip() or "Chanakya@2026"
    target_user.set_password(temp_password)
    target_user.save(update_fields=["password"])
    messages.success(
        request,
        f"Temporary password for {target_user.username} set to '{temp_password}'.",
    )
    return redirect("accounts:admin_users")


@_admin_required
@require_POST
def admin_delete_user_view(request, user_id):
    """Permanently deletes a user account with database cascading (self-deletion blocked)."""
    target_user = get_object_or_404(User, pk=user_id)
    if target_user.pk == request.user.pk:
        messages.error(request, "You cannot delete your own logged-in administrator account.")
        return redirect("accounts:admin_users")

    username = target_user.username
    target_user.delete()
    messages.warning(request, f"User account '{username}' and all associated records were permanently deleted.")
    return redirect("accounts:admin_users")