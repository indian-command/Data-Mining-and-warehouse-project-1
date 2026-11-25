from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from papers.models import Paper, PaperCitation
from research_library.models import SavedResearchItem
from trends.services import EventLogger


def paper_list_view(request):
    """Browses scholarly papers with filtering by source, topic, or year."""
    query = request.GET.get("q", "").strip()
    source_filter = request.GET.get("source", "").strip()
    sort_by = request.GET.get("sort", "pagerank")

    papers = Paper.objects.all()

    if query:
        papers = papers.filter(title__icontains=query)

    if source_filter:
        papers = papers.filter(sources__contains=[source_filter])

    if sort_by == "year":
        papers = papers.order_by("-published_year", "-created_at")
    elif sort_by == "saves":
        papers = papers.order_by("-save_count", "-created_at")
    else:
        papers = papers.order_by("-pagerank_score", "-published_year")

    paginator = Paginator(papers, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "papers/paper_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "source_filter": source_filter,
            "sort_by": sort_by,
        },
    )


def paper_detail_view(request, pk):
    """Detailed view of a paper, its citation connections, and related resources."""
    paper = get_object_or_404(Paper, pk=pk)

    # Log view event for trends and analytics
    if request.user.is_authenticated:
        EventLogger.log_event(
            user=request.user,
            event_type="view_paper",
            target_type="paper",
            target_id=str(paper.id),
            metadata={"title": paper.title},
        )

    # Citations made & received
    citations_made = paper.citations_made.select_related("cited_paper").all()[:10]
    citations_received = paper.citations_received.select_related("citing_paper").all()[:10]

    is_saved = False
    if request.user.is_authenticated and paper.resource:
        is_saved = SavedResearchItem.objects.filter(
            user=request.user, resource=paper.resource
        ).exists()

    # Recommendations: "Members who saved this also saved" from F6
    from recommendations.services import RecommendationService
    also_saved = RecommendationService.get_also_saved_for_paper(paper, limit=5)

    return render(
        request,
        "papers/paper_detail.html",
        {
            "paper": paper,
            "citations_made": citations_made,
            "citations_received": citations_received,
            "is_saved": is_saved,
            "also_saved": also_saved,
        },
    )


@login_required
@require_POST
def save_paper_to_library_view(request, pk):
    """Saves a paper directly into the member's personal Research Library."""
    paper = get_object_or_404(Paper, pk=pk)
    resource = paper.resource

    if not resource:
        from papers.services import IngestionPipeline
        resource = IngestionPipeline._link_research_resource(paper, request.user)

    if resource:
        saved_item, created = SavedResearchItem.objects.get_or_create(
            user=request.user,
            resource=resource,
            defaults={"private_notes": request.POST.get("notes", "").strip()},
        )
        if created:
            Paper.objects.filter(pk=pk).update(save_count=F("save_count") + 1)
            messages.success(request, f"'{paper.title}' was added to your Research Library.")
            EventLogger.log_event(
                user=request.user,
                event_type="save_paper",
                target_type="paper",
                target_id=str(paper.id),
                metadata={"title": paper.title},
            )
        else:
            messages.info(request, "This paper is already in your saved research.")

    return redirect("papers:paper_detail", pk=pk)
