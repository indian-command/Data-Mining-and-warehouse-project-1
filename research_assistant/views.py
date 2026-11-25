from django.shortcuts import render
from research_assistant.services import ResearchAssistantService


def assistant_view(request):
    """Plain-language grounded research assistant Q&A interface with source verification."""
    query = request.GET.get("q", "").strip()
    result = None

    if query:
        result = ResearchAssistantService.ask(question=query, user=request.user)

    return render(
        request,
        "research_assistant/assistant.html",
        {
            "query": query,
            "result": result,
        },
    )
