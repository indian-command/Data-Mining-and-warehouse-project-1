
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path("admin/", admin.site.urls),

    path("accounts/", include("accounts.urls")),
    path("discussions/", include("discussions.urls")),
    path("library/", include("research_library.urls")),
    path("papers/", include("papers.urls")),
    path("search/", include("unified_search.urls")),
    path("recommendations/", include("recommendations.urls")),
    path("trends/", include("trends.urls")),
    path("assistant/", include("research_assistant.urls")),
    path("analytics/", include("institutional_analytics.urls")),
    path("", include("core.urls")),
]


# Serve uploaded files during local development
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
