
from django.urls import path

from . import views


app_name = "research_library"

urlpatterns = [

    path(
        "",
        views.library_home_view,
        name="library_home"
    ),

    path(
        "save/",
        views.save_research_item_view,
        name="save"
    ),

    path(
        "saved/<int:saved_item_id>/notes/",
        views.update_private_note_view,
        name="update_note"
    ),

    path(
        "collections/create/",
        views.create_collection_view,
        name="create_collection"
    ),

    path(
        "collections/add/",
        views.add_to_collection_view,
        name="add_to_collection"
    ),

    path(
        "collections/item/<int:collection_item_id>/remove/",
        views.remove_from_collection_view,
        name="remove_from_collection"
    ),
]
