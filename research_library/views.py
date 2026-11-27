
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .forms import (
    SaveResearchItemForm,
    ResearchCollectionForm,
    AddToCollectionForm,
    ResearchSearchForm,

)


from .models import (
    ResearchResource,
    SavedResearchItem,
    ResearchCollection,
    CollectionItem,
)

from .services import (
    save_research_item,
    search_research_sources,
)

def _library_context(user):

    saved_items = (
        SavedResearchItem.objects
        .filter(user=user)
        .select_related("resource")
        .order_by("-saved_at")
    )


    library_resources = (
        ResearchResource.objects
        .annotate(
            member_save_count=Count(
                "saves__user",
                distinct=True
            )
        )
        .order_by("-member_save_count", "-created_at")
    )

    collections = (
        ResearchCollection.objects
        .filter(owner=user)
        .prefetch_related(
            "items__saved_item__resource"
        )
        .order_by("-created_at")
    )

    return {
        "saved_items": saved_items,
        "library_resources": library_resources,
        "collections": collections,
        "collection_form": ResearchCollectionForm(),
        "add_to_collection_form": AddToCollectionForm(user=user),
        "search_form": ResearchSearchForm(),
        "search_results": [],
        "search_errors": [],
        "search_performed": False,
    }


# ==========================================
# 1. RESEARCH LIBRARY HOME
# ==========================================

@login_required
def library_home_view(request):

    context = _library_context(request.user)
    context["form"] = SaveResearchItemForm()

    search_query = request.GET.get("query", "").strip()

    if search_query:

        search_form = ResearchSearchForm(
            {"query": search_query}
        )

        context["search_form"] = search_form
        context["search_performed"] = True

        if search_form.is_valid():

            results, errors = search_research_sources(
                search_form.cleaned_data["query"]
            )

            context["search_results"] = results
            context["search_errors"] = errors

    return render(
        request,
        "research_library/library_home.html",
        context
    )

# ==========================================
# 2. SAVE RESEARCH ITEM
# ==========================================

@login_required
@require_POST
def save_research_item_view(request):

    form = SaveResearchItemForm(request.POST)

    if not form.is_valid():

        context = _library_context(request.user)
        context["form"] = form

        return render(
            request,
            "research_library/library_home.html",
            context
        )

    try:

        resource, saved_item, created = save_research_item(
            request.user,
            form.cleaned_data
        )

    except ValidationError as error:

        form.add_error(None, "; ".join(error.messages))

        context = _library_context(request.user)
        context["form"] = form

        return render(
            request,
            "research_library/library_home.html",
            context
        )

    if created:

        messages.success(
            request,
            f"'{resource.title}' was saved to your research library."
        )

    else:

        messages.info(
            request,
            f"'{resource.title}' is already in your saved research."
        )

    return redirect("research_library:library_home")


# ==========================================
# 3. UPDATE PRIVATE NOTES
# ==========================================

@login_required
@require_POST
def update_private_note_view(request, saved_item_id):

    saved_item = get_object_or_404(
        SavedResearchItem,
        pk=saved_item_id,
        user=request.user
    )

    saved_item.private_notes = request.POST.get(
        "private_notes", ""
    ).strip()

    saved_item.save(
        update_fields=["private_notes"]
    )

    messages.success(
        request,
        "Your private research notes have been updated."
    )

    return redirect("research_library:library_home")


# ==========================================
# 4. CREATE PERSONAL COLLECTION
# ==========================================

@login_required
@require_POST
def create_collection_view(request):

    form = ResearchCollectionForm(request.POST)

    if form.is_valid():

        collection = form.save(commit=False)
        collection.owner = request.user
        try:
            collection.save()
            messages.success(
                request,
                f"Collection '{collection.name}' created successfully."
            )
        except Exception:
            messages.warning(
                request,
                f"You already have a collection named '{collection.name}'."
            )

    else:

        context = _library_context(request.user)
        context["form"] = SaveResearchItemForm()
        context["collection_form"] = form

        return render(
            request,
            "research_library/library_home.html",
            context
        )

    return redirect("research_library:library_home")


# ==========================================
# 5. ADD SAVED ITEM TO COLLECTION
# ==========================================

@login_required
@require_POST
def add_to_collection_view(request):

    form = AddToCollectionForm(
        request.POST,
        user=request.user
    )

    if form.is_valid():

        collection = form.cleaned_data["collection"]
        saved_item = form.cleaned_data["saved_item"]

        collection_item, created = CollectionItem.objects.get_or_create(
            collection=collection,
            saved_item=saved_item
        )

        if created:

            messages.success(
                request,
                f"'{saved_item.resource.title}' added to '{collection.name}'."
            )

        else:

            messages.info(
                request,
                "This research item is already in that collection."
            )

    else:

        messages.error(
            request,
            "Please select one of your own collections and saved research items."
        )

    return redirect("research_library:library_home")


# ==========================================
# 6. REMOVE ITEM FROM COLLECTION
# ==========================================

@login_required
@require_POST
def remove_from_collection_view(request, collection_item_id):

    collection_item = get_object_or_404(
        CollectionItem,
        pk=collection_item_id,
        collection__owner=request.user,
        saved_item__user=request.user
    )

    collection_item.delete()

    messages.success(
        request,
        "Item removed from the collection. Your saved research is unchanged."
    )

    return redirect("research_library:library_home")
