
import json
import re
from html import unescape
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree
from urllib.parse import urlencode, urlparse

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import ResearchResource, SavedResearchItem


# ==========================================
# 1. FETCH DOI METADATA FROM CROSSREF
# ==========================================

def fetch_crossref_metadata(doi):

    api_url = (
        "https://api.crossref.org/works/"
        + quote(doi, safe="")
    )

    request = Request(
        api_url,
        headers={
            "User-Agent": "ResearchCommons/1.0"
        }
    )

    try:

        with urlopen(request, timeout=15) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError
    ) as error:

        raise ValidationError(
            "Unable to retrieve DOI information from Crossref. "
            "Check the DOI and try again."
        ) from error

    metadata = data.get("message", {})
    titles = metadata.get("title") or []

    if not titles:
        raise ValidationError(
            "No publication title was found for this DOI."
        )

    abstract = metadata.get("abstract", "")

    abstract = re.sub(
        r"<[^>]+>",
        " ",
        abstract
    )

    abstract = unescape(abstract).strip()

    return {
        "title": titles[0].strip(),
        "description": abstract,
        "url": metadata.get(
            "URL",
            f"https://doi.org/{doi}"
        ),
    }


# ==========================================
# 2. FETCH PAPER METADATA FROM ARXIV
# ==========================================

def fetch_arxiv_metadata(arxiv_id):

    api_url = (
        "https://export.arxiv.org/api/query?id_list="
        + quote(arxiv_id, safe="")
        + "&max_results=1"
    )

    request = Request(
        api_url,
        headers={
            "User-Agent": "ResearchCommons/1.0"
        }
    )

    try:

        with urlopen(request, timeout=15) as response:
            xml_data = response.read()

        root = ElementTree.fromstring(xml_data)

    except (
        HTTPError,
        URLError,
        TimeoutError,
        ElementTree.ParseError
    ) as error:

        raise ValidationError(
            "Unable to retrieve paper information from arXiv. "
            "Check the arXiv ID and try again."
        ) from error

    namespace = {
        "atom": "http://www.w3.org/2005/Atom"
    }

    entry = root.find(
        "atom:entry",
        namespace
    )

    if entry is None:
        raise ValidationError(
            "No research paper was found for this arXiv ID."
        )

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
        raise ValidationError(
            "The arXiv response did not contain a paper title."
        )

    title = " ".join(title.split())
    summary = " ".join(summary.split())

    return {
        "title": title,
        "description": summary,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
    }


# ==========================================
# 3. SAVE RESEARCH ITEM
# ==========================================

@transaction.atomic
def save_research_item(user, cleaned_data):

    source_type = cleaned_data["source_type"]
    identifier = cleaned_data["identifier"]

    user_title = cleaned_data.get(
        "title", ""
    ).strip()

    private_notes = cleaned_data.get(
        "private_notes", ""
    ).strip()

    resource = None

    # ----------------------------------
    # A. SAVE USING URL
    # ----------------------------------

    if source_type == "url":

        resource = ResearchResource.objects.filter(
            url=identifier,
            resource_type="link"
        ).first()

        if resource is None:

            resource = ResearchResource.objects.create(
                title=user_title,
                description="",
                resource_type="link",
                url=identifier,
                uploaded_by=user,
            )

    # ----------------------------------
    # B. SAVE USING DOI
    # ----------------------------------

    elif source_type == "doi":

        resource = ResearchResource.objects.filter(
            doi__iexact=identifier
        ).first()

        if resource is None:

            metadata = fetch_crossref_metadata(
                identifier
            )

            resource = ResearchResource.objects.create(
                title=user_title or metadata["title"],
                description=metadata["description"],
                resource_type="link",
                url=metadata["url"],
                doi=identifier,
                uploaded_by=user,
            )

    # ----------------------------------
    # C. SAVE USING ARXIV ID
    # ----------------------------------

    elif source_type == "arxiv":

        resource = ResearchResource.objects.filter(
            arxiv_id__iexact=identifier
        ).first()

        if resource is None:

            metadata = fetch_arxiv_metadata(
                identifier
            )

            resource = ResearchResource.objects.create(
                title=user_title or metadata["title"],
                description=metadata["description"],
                resource_type="link",
                url=metadata["url"],
                arxiv_id=identifier,
                uploaded_by=user,
            )

    # ----------------------------------
    # D. CREATE MEMBER SAVE RECORD
    # ----------------------------------

    saved_item, created = SavedResearchItem.objects.get_or_create(
        user=user,
        resource=resource,
        defaults={
            "private_notes": private_notes
        }
    )

    # Update notes if the member adds new notes
    if not created and private_notes:

        saved_item.private_notes = private_notes

        saved_item.save(
            update_fields=["private_notes"]
        )

    return resource, saved_item, created

# ==========================================
# 4. SEARCH CROSSREF AND ARXIV
# ==========================================

def search_research_sources(query, max_results=5):

    results = []
    errors = []

    # ----------------------------------
    # CROSSREF SEARCH
    # ----------------------------------

    crossref_url = (
        "https://api.crossref.org/works?"
        + urlencode({
            "query.bibliographic": query,
            "rows": max_results,
        })
    )

    request = Request(
        crossref_url,
        headers={
            "User-Agent": "ResearchCommons/1.0"
        }
    )

    try:

        with urlopen(request, timeout=15) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

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

    arxiv_url = (
        "https://export.arxiv.org/api/query?"
        + urlencode({
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
        })
    )

    request = Request(
        arxiv_url,
        headers={
            "User-Agent": "ResearchCommons/1.0"
        }
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

