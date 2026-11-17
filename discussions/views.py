
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError

from .models import DiscussionPost, Comment, PostVote
from .forms import DiscussionPostForm, CommentForm


# =====================================
# 1. COMMUNITY DISCUSSION FEED
# =====================================


@login_required
def post_list_view(request):

    # Fetch discussion posts with their related data
    posts = (
        DiscussionPost.objects
        .select_related("author")
        .prefetch_related(
            "votes",
            "comments__author",
            "comments__replies__author"
        )
        .order_by("-created_at")
    )

    # Find posts already upvoted by the logged-in user
    voted_post_ids = set(
        PostVote.objects.filter(
            user=request.user
        ).values_list("post_id", flat=True)
    )

    # Display the discussion feed
    return render(
        request,
        "discussions/post_list.html",
        {
            "posts": posts,
            "voted_post_ids": voted_post_ids,
        }
    )



# =====================================
# 2. CREATE RESEARCH POST
# =====================================

@login_required
def post_create_view(request):

    if request.method == "POST":

        form = DiscussionPostForm(request.POST)

        if form.is_valid():

            post = form.save(commit=False)

            # Assign the logged-in member as author
            post.author = request.user

            post.save()

            messages.success(
                request,
                "Your research post has been published!"
            )

            return redirect("discussions:post_list")

    else:

        form = DiscussionPostForm()

    return render(
        request,
        "discussions/post_form.html",
        {
            "form": form,
            "page_title": "Create Research Post",
        }
    )


# =====================================
# 3. EDIT OWN POST
# =====================================

@login_required
def post_edit_view(request, post_id):

    post = get_object_or_404(
        DiscussionPost,
        pk=post_id
    )

    if (
        post.author_id != request.user.id
        and not request.user.is_staff
    ):
        messages.error(
            request,
            "You are not allowed to edit this post."
        )

        return redirect("discussions:post_list")

    if request.method == "POST":

        form = DiscussionPostForm(
            request.POST,
            instance=post
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Your post has been updated."
            )

            return redirect("discussions:post_list")

    else:

        form = DiscussionPostForm(instance=post)

    return render(
        request,
        "discussions/post_form.html",
        {
            "form": form,
            "page_title": "Edit Research Post",
            "post": post,
        }
    )


# =====================================
# 4. DELETE POST
# =====================================

@login_required
@require_POST
def post_delete_view(request, post_id):

    post = get_object_or_404(
        DiscussionPost,
        pk=post_id
    )

    if (
        post.author_id != request.user.id
        and not request.user.is_staff
    ):
        messages.error(
            request,
            "You are not allowed to delete this post."
        )

        return redirect("discussions:post_list")

    post.delete()

    messages.success(
        request,
        "The research post has been deleted."
    )

    return redirect("discussions:post_list")


# =====================================
# 5. UPVOTE / REMOVE UPVOTE
# =====================================

@login_required
@require_POST
def toggle_upvote_view(request, post_id):

    post = get_object_or_404(
        DiscussionPost,
        pk=post_id
    )

    vote = PostVote.objects.filter(
        post=post,
        user=request.user
    )

    if vote.exists():

        vote.delete()

        messages.info(
            request,
            "Your upvote has been removed."
        )

    else:

        PostVote.objects.get_or_create(
            post=post,
            user=request.user
        )

        messages.success(
            request,
            "You upvoted this research post!"
        )

    return redirect("discussions:post_list")


# =====================================
# 6. CREATE COMMENT OR REPLY
# =====================================

@login_required
@require_POST
def comment_create_view(request, post_id):

    post = get_object_or_404(
        DiscussionPost,
        pk=post_id
    )

    form = CommentForm(request.POST)

    if not form.is_valid():

        messages.error(
            request,
            "Please enter a valid comment."
        )

        return redirect("discussions:post_list")

    # Check whether this is a reply
    parent_id = request.POST.get("parent_id")

    parent = None

    if parent_id:

        parent = get_object_or_404(
            Comment,
            pk=parent_id,
            post=post,
            parent__isnull=True
        )

    # Prepare comment
    comment = form.save(commit=False)

    comment.post = post
    comment.author = request.user
    comment.parent = parent

    # Run model validation before saving
    try:
        comment.full_clean()
    except ValidationError as error:

        messages.error(
            request,
            "Unable to add comment: " + "; ".join(error.messages)
        )

        return redirect("discussions:post_list")

    comment.save()

    if parent:
        messages.success(
            request,
            "Your reply was added successfully!"
        )
    else:
        messages.success(
            request,
            "Your comment was added successfully!"
        )

    return redirect("discussions:post_list")
