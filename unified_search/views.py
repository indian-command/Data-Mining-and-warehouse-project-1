from django.shortcuts import render
from unified_search.services import UnifiedSearchService


def unified_search_view(request):
    """Unified 4-Panel Search View: Scholarly Sources, Shared Library, Members, and Discussions."""
    query = request.GET.get("q", "").strip()
    active_tab = request.GET.get("tab", "all")

    results = UnifiedSearchService.execute_unified_search(query=query, user=request.user)

    return render(
        request,
        "unified_search/search.html",
        {
            "query": query,
            "active_tab": active_tab,
            "results": results,
            "total_count": results["total_count"],
        },
    )
