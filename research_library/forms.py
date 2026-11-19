
import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from urllib.parse import urlparse
from .models import ResearchCollection, SavedResearchItem
from urllib.parse import urlencode, urlparse


class SaveResearchItemForm(forms.Form):

    SOURCE_CHOICES = [
        ("url", "Website / Research URL"),
        ("doi", "DOI"),
        ("arxiv", "arXiv ID"),
    ]

    source_type = forms.ChoiceField(
        choices=SOURCE_CHOICES,
        widget=forms.Select(attrs={
            "class": "form-select"
        })
    )

    identifier = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter URL, DOI or arXiv ID"
        })
    )

    title = forms.CharField(
        max_length=250,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Required for ordinary URLs"
        })
    )

    private_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Your private notes about this research item"
        })
    )

    def clean(self):

        cleaned_data = super().clean()

        source_type = cleaned_data.get("source_type")
        identifier = cleaned_data.get("identifier", "").strip()
        title = cleaned_data.get("title", "").strip()

        if not source_type or not identifier:
            return cleaned_data

        if source_type == "url":

            try:
                URLValidator(
                    schemes=["http", "https"]
                )(identifier)

            except ValidationError:
                self.add_error(
                    "identifier",
                    "Enter a valid HTTP or HTTPS URL."
                )

            if not title:
                self.add_error(
                    "title",
                    "A title is required when saving a URL."
                )

        elif source_type == "doi":

            identifier = re.sub(
                r"^doi:\s*",
                "",
                identifier,
                flags=re.IGNORECASE
            )

            identifier = re.sub(
                r"^https?://(?:dx\.)?doi\.org/",
                "",
                identifier,
                flags=re.IGNORECASE
            ).strip()

            if not re.fullmatch(
                r"10\.\d{4,9}/\S+",
                identifier,
                flags=re.IGNORECASE
            ):
                self.add_error(
                    "identifier",
                    "Enter a valid DOI, such as 10.1234/example."
                )

            cleaned_data["identifier"] = identifier

        elif source_type == "arxiv":

            identifier = identifier.rstrip("/")

            if identifier.lower().startswith(
                ("https://arxiv.org/", "http://arxiv.org/")
            ):
                parsed = urlparse(identifier)
                identifier = parsed.path.strip("/")

                if identifier.startswith("abs/"):
                    identifier = identifier[4:]

                elif identifier.startswith("pdf/"):
                    identifier = identifier[4:]

                    if identifier.endswith(".pdf"):
                        identifier = identifier[:-4]

            modern_id = r"\d{4}\.\d{4,5}(v\d+)?"
            legacy_id = r"[a-zA-Z.-]+/\d{7}(v\d+)?"

            if not re.fullmatch(
                f"(?:{modern_id}|{legacy_id})",
                identifier
            ):
                self.add_error(
                    "identifier",
                    "Enter a valid arXiv ID, such as 2501.12345."
                )

            cleaned_data["identifier"] = identifier

        cleaned_data["title"] = title
        cleaned_data["private_notes"] = (
            cleaned_data.get("private_notes", "").strip()
        )

        return cleaned_data


# ==========================================
# PERSONAL COLLECTION FORM
# ==========================================

class ResearchCollectionForm(forms.ModelForm):

    class Meta:
        model = ResearchCollection

        fields = [
            "name",
            "description",
        ]

        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Example: Machine Learning Papers"
            }),

            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Describe your research collection..."
            }),
        }

        labels = {
            "name": "Collection Name",
            "description": "Description",
        }


# ==========================================
# ADD SAVED ITEM TO COLLECTION FORM
# ==========================================

class AddToCollectionForm(forms.Form):

    collection = forms.ModelChoiceField(
        queryset=ResearchCollection.objects.none(),
        widget=forms.Select(attrs={
            "class": "form-select"
        }),
        label="Select Collection"
    )

    saved_item = forms.ModelChoiceField(
        queryset=SavedResearchItem.objects.none(),
        widget=forms.Select(attrs={
            "class": "form-select"
        }),
        label="Select Saved Research Item"
    )

    def __init__(self, *args, user=None, **kwargs):

        super().__init__(*args, **kwargs)

        if user is not None:

            # Only show collections belonging to this member
            self.fields["collection"].queryset = (
                ResearchCollection.objects
                .filter(owner=user)
                .order_by("name")
            )

            # Only show research items saved by this member
            self.fields["saved_item"].queryset = (
                SavedResearchItem.objects
                .filter(user=user)
                .select_related("resource")
                .order_by("-saved_at")
            )


class ResearchSearchForm(forms.Form):

    query = forms.CharField(
        max_length=250,
        label="Search Research Papers",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Search machine learning, robotics, IoT, etc."
        })
    )


# ==========================================
# 4. SEARCH CROSSREF AND ARXIV
# ==========================================

def search_research_sources(query, max_results=5):

    results = []
    errors = []

    # ----------------------------------
    # CROSSREF SEARCH
    # ----------------------------------

    crossref_params = urlencode({
        "query.bibliographic": query,
        "rows": max_results,
    })

    crossref_url = (
        "https://api.crossref.org/works?"
        + crossref_params
    )

    request = Request(
        crossref_url,
        headers={"User-Agent": "ResearchCommons/1.0"}
    )

    try:

        with urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))

        items = data.get("message", {}).get("items", [])

        for item in items:

            doi = item.get("DOI")
            titles = item.get("title") or []

            if not doi or not titles:
                continue

            authors = []

            for author in item.get("author", [])[:5]:
                name = " ".join(filter(None, [
                    author.get("given", ""),
                    author.get("family", "")
                ]))

                if name:
                    authors.append(name)

            results.append({
                "provider": "Crossref",
                "source_type": "doi",
                "identifier": doi,
                "title": titles[0],
                "description": (
                    ", ".join(authors)
                    or "Academic publication"
                ),
                "url": f"https://doi.org/{doi}",
            })

    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError
    ):

        errors.append(
            "Crossref search is temporarily unavailable."
        )

    # ----------------------------------
    # ARXIV SEARCH
    # ----------------------------------

    arxiv_params = urlencode({
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
    })

    arxiv_url = (
        "https://export.arxiv.org/api/query?"
        + arxiv_params
    )

    request = Request(
        arxiv_url,
        headers={"User-Agent": "ResearchCommons/1.0"}
    )

    try:

        with urlopen(request, timeout=15) as response:
            xml_data = response.read()

        root = ElementTree.fromstring(xml_data)

        namespace = {
            "atom": "http://www.w3.org/2005/Atom"
        }

        entries = root.findall(
            "atom:entry",
            namespace
        )

        for entry in entries:

            paper_url = entry.findtext(
                "atom:id",
                default="",
                namespaces=namespace
            )

            parsed = urlparse(paper_url)
            path = parsed.path

            if "/abs/" not in path:
                continue

            arxiv_id = path.split("/abs/", 1)[1]

            if not arxiv_id:
                continue

            title = entry.findtext(
                "atom:title",
                default="",
                namespaces=namespace
            )

            summary = entry.findtext(
                "atom:summary",
                default="",
                namespaces=namespace
            )

            if not title.strip():
                continue

            results.append({
                "provider": "arXiv",
                "source_type": "arxiv",
                "identifier": arxiv_id,
                "title": " ".join(title.split()),
                "description": " ".join(summary.split()),
                "url": f"https://arxiv.org/abs/{arxiv_id}",
            })

    except (
        HTTPError,
        URLError,
        TimeoutError,
        ElementTree.ParseError
    ):

        errors.append(
            "arXiv search is temporarily unavailable."
        )

    return results, errors
