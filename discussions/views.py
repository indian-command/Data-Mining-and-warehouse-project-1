from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
from django.db.models import Count

from accounts.models import (
    MemberFollow,
    TopicFollow,
    Topic,
    Profile,
)


from .models import DiscussionPost, Comment, PostVote
from .forms import DiscussionPostForm, CommentForm




# =====================================
# 1. COMMUNITY DISCUSSION FEED
# =====================================



@login_required
def post_list_view(request):

    # Base discussion posts with related data loaded efficiently
    base_posts = (
        DiscussionPost.objects
        .select_related("author")
        .prefetch_related(
            "votes",
            "tags",
            "resources",
            "comments__author",
            "comments__replies__author"
        )
        .order_by("-created_at")
    )

    # Members followed by the current user
    followed_member_ids = list(
        MemberFollow.objects.filter(
            follower=request.user
        ).values_list("followed_id", flat=True)
    )

    # Topics followed by the current user
    followed_topic_ids = list(
        TopicFollow.objects.filter(
            user=request.user
        ).values_list("topic_id", flat=True)
    )

    # 1. POSTS FROM FOLLOWED MEMBERS
    following_posts = base_posts.filter(
        author_id__in=followed_member_ids
    ).order_by("-created_at")

    # 2. POSTS MATCHING FOLLOWED TOPICS
    topic_posts = (
        base_posts
        .filter(tags__id__in=followed_topic_ids)
        .distinct()
        .order_by("-created_at")
    )

    # 3. RECOMMENDED POSTS
    # Start with posts not already covered by the other two feeds
    recommended_base = base_posts.exclude(
        author=request.user
    )

    if followed_member_ids:
        recommended_base = recommended_base.exclude(
            author_id__in=followed_member_ids
        )

    if followed_topic_ids:
        recommended_base = recommended_base.exclude(
            tags__id__in=followed_topic_ids
        )

    # Get the research interests selected in the user's profile
    profile_topic_ids = list(
        Profile.objects.filter(
            user=request.user
        ).values_list("topics__id", flat=True)
    )

    # Prefer posts matching the user's research interests
    if profile_topic_ids:

        relevant_posts = (
            recommended_base
            .filter(tags__id__in=profile_topic_ids)
            .distinct()
        )

        # If there are no matching posts, use community activity
        if relevant_posts.exists():
            recommended_candidates = relevant_posts
        else:
            recommended_candidates = recommended_base

    else:
        recommended_candidates = recommended_base

    # Rank recommendations by upvotes, comments and recency
    recommended_posts = (
        recommended_candidates
        .annotate(
            feed_upvotes=Count("votes", distinct=True),
            feed_comments=Count("comments", distinct=True)
        )
        .order_by(
            "-feed_upvotes",
            "-feed_comments",
            "-created_at"
        )
    )


    # Choose which personalized feed to display
    feed_type = request.GET.get("feed", "recommended")

    # My own research posts
    my_posts = base_posts.filter(
        author=request.user
    )

    if feed_type == "my_posts":

        posts = my_posts
        feed_title = "My Research Posts"

    elif feed_type == "following":

        posts = following_posts
        feed_title = "Posts from Members You Follow"

    elif feed_type == "topics":

        posts = topic_posts
        feed_title = "Posts from Your Followed Topics"

    else:

        feed_type = "recommended"
        posts = recommended_posts
        feed_title = "Recommended Research Posts"

    # Posts already upvoted by the current user
    voted_post_ids = set(
        PostVote.objects.filter(
            user=request.user
        ).values_list("post_id", flat=True)
    )

    # Topics available for following
    all_topics = Topic.objects.all()

    return render(
        request,
        "discussions/post_list.html",
        {
            "posts": posts,
            "voted_post_ids": voted_post_ids,
            "feed_type": feed_type,
            "feed_title": feed_title,
            "all_topics": all_topics,
            "followed_topic_ids": set(followed_topic_ids),
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

            # Save selected research topics
            form.save_m2m()

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
