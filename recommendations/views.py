from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from recommendations.services import RecommendationService


@login_required
def recommendations_home_view(request):
    """Personalized recommendations portal: Papers, Member Matches, and Department Trends."""
    user = request.user
    paper_recs = RecommendationService.get_recommended_papers(user, limit=12)
    member_recs = RecommendationService.get_member_recommendations(user, limit=6)

    return render(
        request,
        "recommendations/recommendations_home.html",
        {
            "paper_recs": paper_recs["papers"],
            "strategy_label": paper_recs["label"],
            "strategy": paper_recs["strategy"],
            "member_recs": member_recs,
        },
    )
