import csv
import io
import json
import logging
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

import feedparser
import networkx as nx
import pyarrow as pa
import pyarrow.parquet as pq
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from minio import Minio
from minio.error import S3Error
from sentence_transformers import SentenceTransformer

from papers.models import Paper, PaperChunk, PaperCitation
from research_library.models import ResearchResource

logger = logging.getLogger(__name__)
User = get_user_model()


# =====================================================================
# 1. MinIO S3 Storage Service
# =====================================================================

class MinIOService:
    """Manages raw payload and analytical Parquet storage in MinIO S3."""

    _instance = None

    @classmethod
    def get_client(cls) -> Optional[Minio]:
        if cls._instance is None:
            try:
                cls._instance = Minio(
                    settings.MINIO_ENDPOINT,
                    access_key=settings.MINIO_ROOT_USER,
                    secret_key=settings.MINIO_ROOT_PASSWORD,
                    secure=settings.MINIO_SECURE,
                )
                # Ensure buckets exist
                for bucket in [settings.MINIO_BUCKET_RAW, settings.MINIO_BUCKET_PARQUET]:
                    if not cls._instance.bucket_exists(bucket):
                        cls._instance.make_bucket(bucket)
            except Exception as e:
                logger.warning(f"MinIO connection failed: {e}. Will use local fallback storage.")
                cls._instance = None
        return cls._instance

    @classmethod
    def upload_raw(cls, source: str, identifier: str, data: bytes | str, content_type: str = "application/json") -> str:
        """Stores raw unmodified JSON/XML payload with timestamps and source metadata."""
        if isinstance(data, str):
            payload_bytes = data.encode("utf-8")
        else:
            payload_bytes = data

        timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_id = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", identifier)[:80]
        ext = "xml" if "xml" in content_type else "json"
        object_name = f"raw/{source}/{datetime.utcnow().strftime('%Y-%m')}/{timestamp_str}_{safe_id}.{ext}"

        client = cls.get_client()
        if client:
            try:
                stream = io.BytesIO(payload_bytes)
                client.put_object(
                    bucket_name=settings.MINIO_BUCKET_RAW,
                    object_name=object_name,
                    data=stream,
                    length=len(payload_bytes),
                    content_type=content_type,
                    metadata={"source": source, "identifier": identifier, "ingested_at": timestamp_str},
                )
                return object_name
            except Exception as e:
                logger.error(f"Failed to upload raw payload to MinIO: {e}")

        # Local fallback persistence
        fallback_dir = settings.BASE_DIR / "data" / "raw_fallback" / source
        fallback_dir.mkdir(parents=True, exist_ok=True)
        fallback_path = fallback_dir / f"{timestamp_str}_{safe_id}.{ext}"
        fallback_path.write_bytes(payload_bytes)
        return str(fallback_path)

    @classmethod
    def upload_parquet(cls, object_name: str, parquet_bytes: bytes) -> str:
        """Uploads star-schema or analytics Parquet file to MinIO."""
        client = cls.get_client()
        if client:
            try:
                stream = io.BytesIO(parquet_bytes)
                client.put_object(
                    bucket_name=settings.MINIO_BUCKET_PARQUET,
                    object_name=object_name,
                    data=stream,
                    length=len(parquet_bytes),
                    content_type="application/octet-stream",
                )
                return object_name
            except Exception as e:
                logger.error(f"Failed to upload parquet to MinIO: {e}")

        # Local fallback persistence
        fallback_path = settings.ANALYTICS_DATA_DIR / object_name.split("/")[-1]
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        fallback_path.write_bytes(parquet_bytes)
        return str(fallback_path)


# =====================================================================
# 2. Embedding & Chunking Services
# =====================================================================

class EmbeddingService:
    """Generates 384-dimensional embeddings via sentence-transformers/all-MiniLM-L6-v2."""

    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            try:
                cls._model = SentenceTransformer(settings.EMBEDDING_MODEL)
            except Exception as e:
                logger.error(f"Could not load SentenceTransformer model: {e}")
                cls._model = None
        return cls._model

    @classmethod
    def generate_embedding(cls, text: str) -> List[float]:
        """Encodes text into a normalized 384-d float list."""
        if not text or not text.strip():
            return [0.0] * 384

        model = cls.get_model()
        if model is not None:
            try:
                emb = model.encode(text.strip(), normalize_embeddings=True)
                return emb.tolist()
            except Exception as e:
                logger.warning(f"Model encoding failed: {e}. Falling back to deterministic embedding.")

        # Deterministic fallback embedding for offline or test environments
        import hashlib
        import math
        vec = [0.0] * 384
        for word in text.lower().split():
            h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
            idx = h % 384
            val = ((h >> 8) % 1000) / 1000.0 - 0.5
            vec[idx] += val
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    @classmethod
    def generate_batch(cls, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        model = cls.get_model()
        if model is not None:
            try:
                embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
                return [e.tolist() for e in embs]
            except Exception as e:
                logger.warning(f"Batch embedding failed: {e}")
        return [cls.generate_embedding(t) for t in texts]


class TextChunker:
    """Chunks paper text and abstracts into overlapping passages for RAG Q&A (F8)."""

    @staticmethod
    def chunk_text(text: str, chunk_size_words: int = 150, overlap_words: int = 30) -> List[str]:
        words = text.strip().split()
        if not words:
            return []
        if len(words) <= chunk_size_words:
            return [" ".join(words)]

        chunks = []
        step = max(1, chunk_size_words - overlap_words)
        for i in range(0, len(words), step):
            chunk = " ".join(words[i : i + chunk_size_words])
            chunks.append(chunk)
            if i + chunk_size_words >= len(words):
                break
        return chunks


# =====================================================================
# 3. External API Ingesters (OpenAlex, arXiv, RSS)
# =====================================================================

class OpenAlexIngester:
    """Fetches scholarly publications and citation links from OpenAlex API."""

    BASE_URL = "https://api.openalex.org/works"

    @classmethod
    def fetch(cls, query: str = "artificial intelligence", limit: int = 25) -> List[Dict[str, Any]]:
        params = {
            "search": query,
            "per-page": min(limit, 50),
            "sort": "relevance_score:desc",
        }
        headers = {"User-Agent": "ChanakyaResearchCommons/1.0 (mailto:research@chanakya.edu.in)"}

        try:
            resp = requests.get(cls.BASE_URL, params=params, headers=headers, timeout=12)
            if resp.status_code != 200:
                logger.warning(f"OpenAlex returned status {resp.status_code}")
                return []
            data = resp.json()
            raw_json_str = resp.text
            MinIOService.upload_raw("openalex", query, raw_json_str, "application/json")
        except Exception as e:
            logger.error(f"OpenAlex request failed: {e}")
            return []

        results = []
        for item in data.get("results", []):
            openalex_id = item.get("id", "").replace("https://openalex.org/", "")
            doi = item.get("doi")
            if doi:
                doi = doi.replace("https://doi.org/", "").strip()

            # Invert OpenAlex abstract index
            abstract = ""
            inv_index = item.get("abstract_inverted_index")
            if inv_index:
                word_positions: List[Tuple[int, str]] = []
                for word, pos_list in inv_index.items():
                    for pos in pos_list:
                        word_positions.append((pos, word))
                word_positions.sort(key=lambda x: x[0])
                abstract = " ".join(w for _, w in word_positions)

            # Authors
            authors = []
            for authorship in item.get("authorships", []):
                author_name = authorship.get("author", {}).get("display_name")
                if author_name:
                    authors.append(author_name)

            title = item.get("title") or item.get("display_name") or "Untitled Paper"
            year = item.get("publication_year")
            venue = item.get("primary_location", {}).get("source", {}).get("display_name") or ""
            landing_url = item.get("primary_location", {}).get("landing_page_url") or (f"https://doi.org/{doi}" if doi else "")
            referenced_works = [rw.replace("https://openalex.org/", "") for rw in item.get("referenced_works", [])]

            results.append({
                "openalex_id": openalex_id,
                "canonical_doi": doi or None,
                "title": title.strip(),
                "authors": authors,
                "abstract": abstract.strip(),
                "published_year": year,
                "venue": venue,
                "url": landing_url,
                "sources": ["openalex"],
                "referenced_ids": referenced_works,
            })
        return results


class ArxivIngester:
    """Fetches papers from arXiv API with metadata and summaries."""

    BASE_URL = "https://export.arxiv.org/api/query"

    @classmethod
    def fetch(cls, query: str = "computer science", limit: int = 25) -> List[Dict[str, Any]]:
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": min(limit, 50),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        headers = {"User-Agent": "ChanakyaResearchCommons/1.0"}

        try:
            resp = requests.get(cls.BASE_URL, params=params, headers=headers, timeout=12)
            if resp.status_code != 200:
                logger.warning(f"arXiv API returned status {resp.status_code}")
                return []
            raw_xml = resp.text
            MinIOService.upload_raw("arxiv", query, raw_xml, "application/xml")
            feed = feedparser.parse(raw_xml)
        except Exception as e:
            logger.error(f"arXiv request failed: {e}")
            return []

        results = []
        for entry in feed.entries:
            arxiv_url = entry.get("id", "")
            arxiv_id = arxiv_url.split("/abs/")[-1] if "/abs/" in arxiv_url else arxiv_url.split("/")[-1]
            # Strip version e.g. 2104.12345v1 -> 2104.12345
            clean_arxiv_id = re.sub(r"v\d+$", "", arxiv_id)

            title = " ".join(entry.get("title", "").split())
            summary = " ".join(entry.get("summary", "").split())
            authors = [a.get("name") for a in entry.get("authors", []) if a.get("name")]
            doi = entry.get("arxiv_doi")

            pub_year = None
            if "published_parsed" in entry and entry.published_parsed:
                pub_year = entry.published_parsed.tm_year

            results.append({
                "arxiv_id": clean_arxiv_id,
                "canonical_doi": doi.strip() if doi else None,
                "title": title,
                "authors": authors,
                "abstract": summary,
                "published_year": pub_year,
                "venue": "arXiv preprint",
                "url": f"https://arxiv.org/abs/{clean_arxiv_id}",
                "sources": ["arxiv"],
                "referenced_ids": [],
            })
        return results


class RSSIngester:
    """Ingests research updates from curated open-access academic and technical RSS feeds."""

    CURATED_FEEDS = [
        ("MIT News AI", "https://news.mit.edu/rss/topic/artificial-intelligence2"),
        ("Nature Biotechnology", "https://www.nature.com/nbt.rss"),
        ("arXiv CS.AI", "https://rss.arxiv.org/rss/cs.AI"),
    ]

    @classmethod
    def fetch(cls, feed_url: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        target_feeds = [feed_url] if feed_url else [url for _, url in cls.CURATED_FEEDS]
        results = []

        for url in target_feeds:
            try:
                feed = feedparser.parse(url)
                MinIOService.upload_raw("rss", url, json.dumps(feed.entries[:limit], default=str), "application/json")
                for entry in feed.entries[:limit]:
                    title = " ".join(entry.get("title", "").split())
                    summary = " ".join(re.sub(r"<[^>]+>", " ", entry.get("summary", "")).split())
                    link = entry.get("link", "")

                    pub_year = None
                    if "published_parsed" in entry and entry.published_parsed:
                        pub_year = entry.published_parsed.tm_year

                    authors = []
                    if "author" in entry and entry.author:
                        authors = [entry.author]

                    results.append({
                        "title": title,
                        "authors": authors or ["Research Staff"],
                        "abstract": summary,
                        "published_year": pub_year or timezone.now().year,
                        "venue": feed.feed.get("title", "Academic RSS Feed"),
                        "url": link,
                        "sources": ["rss"],
                        "canonical_doi": None,
                        "arxiv_id": None,
                        "openalex_id": None,
                        "referenced_ids": [],
                    })
            except Exception as e:
                logger.error(f"Failed to fetch RSS feed {url}: {e}")

        return results


class ChanakyaUniversityIngester:
    """
    Polite, production-clean ingester for authentic Chanakya University faculty and centre research publications.
    Collects scholarly works from:
    1. Chanakya University Publications Directory (backed by Google Sheets live database)
    2. Centre for Indian Knowledge Systems (CIKS) Research Papers
    3. School of Biosciences (SBS) Journals
    4. Public Faculty Profile Pages under /faculties/
    """

    HEADERS = {
        "User-Agent": "ChanakyaResearchCommonsBot/1.0 (+http://localhost:8080/; mailto:research@chanakya.edu.in)"
    }

    @staticmethod
    def _clean_text(s: str) -> str:
        if not s:
            return ""
        s = re.sub(r"&[a-zA-Z0-9#]+;", " ", s)
        s = re.sub(r"\s+", " ", s)
        return s.strip(" \t\r\n\"'“”)(")

    @staticmethod
    def _extract_doi(text: str) -> str:
        if not text:
            return ""
        match = re.search(r"\b(10\.\d{4,9}/[^\s,;\"'<>]+)", text)
        if match:
            doi = match.group(1).rstrip(".):;")
            return doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
        return ""

    @staticmethod
    def _extract_year(text: str) -> int:
        if not text:
            return 2024
        matches = re.findall(r"\b(20[12]\d)\b", str(text))
        if matches:
            return int(matches[-1])
        return 2024

    @staticmethod
    def _parse_authors(author_str: str) -> List[str]:
        if not author_str:
            return ["Chanakya University Faculty"]
        cleaned = re.sub(r"\b(Dr\.|Prof\.|Sri\.|Smt\.|Mr\.|Ms\.)\s*", "", author_str)
        parts = re.split(r"[,;&\n]|\band\b", cleaned)
        authors = []
        for p in parts:
            p = ChanakyaUniversityIngester._clean_text(p)
            if len(p) > 2 and not p.lower().startswith("et al"):
                authors.append(p)
        return authors or [ChanakyaUniversityIngester._clean_text(author_str)]

    @staticmethod
    def _normalize_title(title: str) -> str:
        cleaned = re.sub(r"\(.*?\)|\[.*?\]", "", title)
        return re.sub(r"[^a-zA-Z0-9]", "", cleaned.lower())

    @classmethod
    def fetch_google_sheet_publications(cls) -> List[Dict[str, Any]]:
        url = "https://docs.google.com/spreadsheets/d/1EKsR-6gIl0yaPH9v61-Trs7xie1IMbtmPsn-YJsV3wM/export?format=csv&gid=0"
        try:
            resp = requests.get(url, headers=cls.HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Chanakya sheet export returned status {resp.status_code}")
                return []
            reader = csv.DictReader(io.StringIO(resp.text))
            pubs = []
            for row in reader:
                title = cls._clean_text(row.get("Title of the paper", "")).strip(" ,.;:\"'“”")
                if not title or len(title) < 5:
                    continue
                primary_author = cls._clean_text(row.get("Name of the Author", ""))
                co_authors = cls._clean_text(row.get("Co-author", ""))
                authors = cls._parse_authors(f"{primary_author}, {co_authors}" if co_authors else primary_author)

                dept = cls._clean_text(row.get("Department", "")) or "School of Arts, Humanities and Social Sciences"
                journal = cls._clean_text(row.get("Name of the Journal", ""))
                year = cls._extract_year(row.get("Year in which it was published", ""))

                raw_doi_isbn = row.get("ISBN/ISSN/DOI", "")
                link = cls._clean_text(row.get("Link", ""))
                doi = cls._extract_doi(raw_doi_isbn) or cls._extract_doi(link)

                url_target = link if (link.startswith("http://") or link.startswith("https://")) else ""
                if doi and not url_target:
                    url_target = f"https://doi.org/{doi}"
                if not url_target:
                    url_target = f"https://scholar.google.com/scholar?q={urllib.parse.quote(title)}"

                abstract = cls._clean_text(row.get("Abstract (as copied from linked document)", ""))
                if not abstract or len(abstract) < 30:
                    abstract = (
                        f"Scholarly publication titled '{title}', authored by {', '.join(authors[:3])} in "
                        f"{journal or 'Academic Journal'} ({year}). Research conducted within the {dept} at Chanakya University."
                    )

                pubs.append({
                    "title": title,
                    "authors": authors,
                    "published_year": year,
                    "venue": journal or f"Chanakya University Research Series ({dept})",
                    "doi": doi or None,
                    "url": url_target,
                    "abstract": abstract,
                    "school_centre": dept,
                    "source": "chanakya_university",
                })
            return pubs
        except Exception as e:
            logger.error(f"Failed to fetch Chanakya University publication sheet: {e}")
            return []

    @classmethod
    def fetch_ciks_publications(cls) -> List[Dict[str, Any]]:
        url = "https://chanakyauniversity.edu.in/ciks/publication/research-papers/"
        try:
            resp = requests.get(url, headers=cls.HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"CIKS papers page returned status {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            papers = []
            for h in soup.find_all(["h2", "h3", "h4"]):
                parent = h.parent
                text = parent.get_text(separator="\n", strip=True)
                if any(k in text for k in ["Author", "Year", "Institution", "Journal"]):
                    title = cls._clean_text(h.get_text(strip=True)).strip(" ,.;:\"'“”")
                    if len(title) < 5 or "Research Papers" in title:
                        continue
                    authors_match = re.findall(r"Author\(s\)\s*:\s*(.+)", text)
                    authors = cls._parse_authors(authors_match[0] if authors_match else "")
                    year_match = re.findall(r"Year\s*:\s*(.+)", text)
                    year = cls._extract_year(year_match[0] if year_match else "")
                    inst_match = re.findall(r"Institution\s*:\s*(.+)", text)
                    dept = cls._clean_text(inst_match[0] if inst_match else "Centre for Indian Knowledge Systems (CIKS)")
                    journal_match = re.findall(r"Name of the Journal\s*:\s*(.+)", text)
                    venue = cls._clean_text(journal_match[0] if journal_match else "Journal of Indic Studies")

                    doi = ""
                    url_target = ""
                    for a in parent.find_all("a", href=True):
                        href = a["href"].strip()
                        if "doi.org" in href or "10." in href:
                            doi = cls._extract_doi(href)
                            url_target = f"https://doi.org/{doi}"
                        elif href.startswith("http") and not url_target:
                            url_target = href

                    if not doi:
                        doi = cls._extract_doi(text)
                    if doi and not url_target:
                        url_target = f"https://doi.org/{doi}"
                    if not url_target:
                        url_target = f"https://scholar.google.com/scholar?q={urllib.parse.quote(title)}"

                    abstract = (
                        f"Research publication on '{title}' by {', '.join(authors[:3])}, published in {venue} ({year}). "
                        f"Explores authentic methodologies and critical insights at the {dept}, Chanakya University."
                    )
                    papers.append({
                        "title": title,
                        "authors": authors,
                        "published_year": year,
                        "venue": venue,
                        "doi": doi or None,
                        "url": url_target,
                        "abstract": abstract,
                        "school_centre": dept,
                        "source": "chanakya_university",
                    })
            return papers
        except Exception as e:
            logger.error(f"Failed to fetch CIKS publications: {e}")
            return []

    @classmethod
    def fetch_bioscience_publications(cls) -> List[Dict[str, Any]]:
        url = "https://chanakyauniversity.edu.in/bioscience/journals/"
        try:
            resp = requests.get(url, headers=cls.HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Bioscience journals page returned status {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            papers = []
            current_year = 2025
            for tag in soup.find_all(["h2", "h3", "h4", "p", "li"]):
                txt = tag.get_text(" ", strip=True)
                if re.match(r"^202[0-9]$", txt.strip()):
                    current_year = int(txt.strip())
                    continue
                doi_a = tag.find("a", href=lambda h: h and "doi.org" in h)
                if doi_a or (re.search(r"\b202[0-6]\b", txt) and len(txt) > 50 and any(k in txt.lower() for k in ["et al", "doi", "vol", "pp.", "pharmaceutics", "nature", "springer", "elsevier", "frontiers"])):
                    if any(bad in txt.lower() for bad in ["all rights reserved", "mandatory disclosure", "admission", "quick links"]):
                        continue
                    doi = cls._extract_doi(doi_a["href"] if doi_a else txt)
                    parts = [cls._clean_text(p) for p in re.split(r"\.\s+|\.\s*$", txt) if len(cls._clean_text(p)) > 5]
                    if len(parts) >= 2:
                        authors_part = parts[0]
                        title_part = parts[1] if len(parts) > 1 else txt[:80]
                        venue_part = parts[2] if len(parts) > 2 else "School of Biosciences Journal Series"
                    else:
                        title_part = txt[:120]
                        authors_part = "School of Biosciences Researchers"
                        venue_part = "School of Biosciences Journal Series"

                    authors = cls._parse_authors(authors_part)
                    title = cls._clean_text(title_part).strip(" ,.;:\"'“”")
                    if len(title) < 10:
                        continue
                    year = cls._extract_year(txt) or current_year
                    url_target = f"https://doi.org/{doi}" if doi else (doi_a["href"] if doi_a else f"https://scholar.google.com/scholar?q={urllib.parse.quote(title)}")
                    abstract = (
                        f"School of Biosciences research article titled '{title}', authored by {', '.join(authors[:3])} in "
                        f"{venue_part} ({year}). Focuses on biological and biomolecular investigations at Chanakya University."
                    )
                    papers.append({
                        "title": title,
                        "authors": authors,
                        "published_year": year,
                        "venue": venue_part,
                        "doi": doi or None,
                        "url": url_target,
                        "abstract": abstract,
                        "school_centre": "School of Biosciences",
                        "source": "chanakya_university",
                    })
            return papers
        except Exception as e:
            logger.error(f"Failed to fetch Bioscience publications: {e}")
            return []

    @classmethod
    def fetch_faculty_profile_publications(cls, limit: int = 50) -> List[Dict[str, Any]]:
        url = "https://chanakyauniversity.edu.in/faculties/"
        try:
            resp = requests.get(url, headers=cls.HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Faculty directory page returned status {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            unique_fac = {}
            for a in soup.find_all("a", href=True):
                href = a["href"].rstrip("/")
                if "chanakyauniversity.edu.in/faculties/" in href and href != "https://chanakyauniversity.edu.in/faculties":
                    card = a.find_parent(["div", "article"])
                    text = card.get_text(" | ", strip=True) if card else ""
                    name = a.get_text(strip=True)
                    if name and len(name) > 3 and href not in unique_fac:
                        school = "School of Arts, Humanities and Social Sciences"
                        if "Biosciences" in text:
                            school = "School of Biosciences"
                        elif "Management" in text or "Commerce" in text:
                            school = "School of Management Sciences"
                        elif "Law" in text or "Public Policy" in text:
                            school = "School of Law, Governance and Public Policy"
                        elif "Indian Knowledge" in text or "CIKS" in text:
                            school = "Centre for Indian Knowledge Systems"
                        elif "Mathematics" in text or "Natural Sciences" in text:
                            school = "School of Mathematics and Natural Sciences"
                        elif "Engineering" in text or "Computing" in text:
                            school = "School of Engineering"
                        unique_fac[href] = (name, school, href + "/")

            target_fac = list(unique_fac.values())[:limit]

            def fetch_single_profile(fac_info):
                name, school, profile_url = fac_info
                try:
                    r = requests.get(profile_url, headers=cls.HEADERS, timeout=8)
                    if r.status_code != 200:
                        return []
                    s = BeautifulSoup(r.text, "html.parser")
                    pubs = []
                    for tag in s.find_all(["h2", "h3", "h4", "h5"]):
                        if "publication" in tag.get_text().lower():
                            parent = tag.find_next_sibling() or tag.parent
                            for li in parent.find_all(["li", "p"]):
                                txt = li.get_text(" ", strip=True)
                                if len(txt) > 35 and any(y in txt for y in ["201", "202"]):
                                    quote_m = re.search(r"[\u201c\"]([^\u201d\"]+)[\u201d\"]", txt)
                                    if quote_m:
                                        title = cls._clean_text(quote_m.group(1))
                                        before_q = txt[:quote_m.start()].strip(" ,.")
                                        after_q = txt[quote_m.end():].strip(" ,.")
                                        authors = [a.strip() for a in re.split(r"[,;&]|\band\b", before_q) if len(a.strip()) > 2]
                                        if not authors:
                                            authors = [name]
                                        venue = cls._clean_text(after_q.split(".")[0]) if after_q else "Academic Journal"
                                    else:
                                        parts = [cls._clean_text(p) for p in txt.split(".") if len(cls._clean_text(p)) > 5]
                                        if len(parts) >= 3:
                                            authors = [name]
                                            title = parts[1]
                                            venue = parts[2]
                                        else:
                                            continue
                                    title = cls._clean_text(title).strip(" ,.;:\"'“”")
                                    if len(title) < 10 or any(b in title.lower() for b in ["all rights reserved", "curriculum vitae", "ph.d"]):
                                        continue
                                    doi = cls._extract_doi(txt)
                                    year = cls._extract_year(txt)
                                    url_target = f"https://doi.org/{doi}" if doi else f"https://scholar.google.com/scholar?q={urllib.parse.quote(title)}"
                                    abstract = (
                                        f"Faculty research publication titled '{title}', authored by {name} et al. in {venue} ({year}). "
                                        f"Department: {school}, Chanakya University."
                                    )
                                    pubs.append({
                                        "title": title,
                                        "authors": authors,
                                        "published_year": year,
                                        "venue": venue,
                                        "doi": doi or None,
                                        "url": url_target,
                                        "abstract": abstract,
                                        "school_centre": school,
                                        "source": "chanakya_university",
                                    })
                    return pubs
                except Exception:
                    return []

            results = []
            with ThreadPoolExecutor(max_workers=6) as executor:
                for fac_pubs in executor.map(fetch_single_profile, target_fac):
                    results.extend(fac_pubs)
            return results
        except Exception as e:
            logger.error(f"Failed to fetch faculty profile publications: {e}")
            return []

    @classmethod
    def fetch_all_publications(cls, faculty_limit: int = 50) -> List[Dict[str, Any]]:
        """
        Aggregates and deduplicates publications from all 4 Chanakya University portals,
        archives raw payload to data/ and MinIO, and returns the normalized list.
        """
        logger.info("Fetching Chanakya University publications across all 4 sources...")
        raw_items: List[Dict[str, Any]] = []

        # 1. Official Directory (Google Sheet export)
        sheet_pubs = cls.fetch_google_sheet_publications()
        raw_items.extend(sheet_pubs)

        # 2. CIKS Research Papers
        ciks_pubs = cls.fetch_ciks_publications()
        raw_items.extend(ciks_pubs)

        # 3. School of Biosciences Journals
        bio_pubs = cls.fetch_bioscience_publications()
        raw_items.extend(bio_pubs)

        # 4. Faculty Profiles
        fac_pubs = cls.fetch_faculty_profile_publications(limit=faculty_limit)
        raw_items.extend(fac_pubs)

        # Internal deduplication
        seen_dois = set()
        seen_titles = set()
        deduped: List[Dict[str, Any]] = []

        for p in raw_items:
            doi = p.get("doi")
            norm_t = cls._normalize_title(p["title"])
            if doi and doi.lower() in seen_dois:
                continue
            if norm_t and norm_t in seen_titles:
                continue
            if doi:
                seen_dois.add(doi.lower())
            if norm_t:
                seen_titles.add(norm_t)
            deduped.append(p)

        # Raw lakehouse archival
        try:
            raw_payload_json = json.dumps(deduped, indent=2, default=str)
            raw_path = settings.BASE_DIR / "data" / "chanakya_univ_publications_raw.json"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(raw_payload_json, encoding="utf-8")
            MinIOService.upload_raw("chanakya_university", "chanakya_publications", raw_payload_json, "application/json")
        except Exception as e:
            logger.warning(f"Could not archive raw Chanakya publications to lakehouse: {e}")

        logger.info(f"Collected {len(deduped)} unique publications from Chanakya University.")
        return deduped

    @classmethod
    def find_faculty_user(cls, author_names: List[str], school_centre: str = "") -> Optional[Any]:
        User = get_user_model()
        all_users = list(User.objects.filter(profile__isnull=False).select_related("profile"))

        # 1. Exact full name match
        for author in author_names:
            cleaned = re.sub(r"\b(Dr\.|Prof\.|Sri\.|Smt\.|Mr\.|Ms\.)\s*", "", author).strip()
            for u in all_users:
                full = u.get_full_name().strip()
                if full and full.lower() == cleaned.lower():
                    return u

        # 2. Matching last name and first initial
        for author in author_names:
            cleaned = re.sub(r"\b(Dr\.|Prof\.|Sri\.|Smt\.|Mr\.|Ms\.)\s*", "", author).strip()
            parts = cleaned.split()
            if len(parts) >= 2:
                last = parts[-1].lower()
                first_init = parts[0][0].lower()
                for u in all_users:
                    u_last = (u.last_name or "").lower()
                    u_first = (u.first_name or "").lower()
                    if u_last == last and u_first and u_first[0] == first_init:
                        return u
        return None

    @classmethod
    def link_faculty_publication(cls, paper: Paper, author_names: List[str], school_centre: str = "") -> None:
        from research_library.models import SavedResearchItem
        User = get_user_model()
        faculty_user = cls.find_faculty_user(author_names, school_centre)
        if not faculty_user:
            faculty_user = User.objects.filter(is_staff=True).first() or User.objects.first()

        IngestionPipeline._link_research_resource(paper, faculty_user)

        if faculty_user and paper.resource:
            SavedResearchItem.objects.get_or_create(
                user=faculty_user,
                resource=paper.resource,
                defaults={"private_notes": f"Faculty research publication in {school_centre or 'Chanakya University'}."}
            )

    @classmethod
    def assign_topics(cls, paper: Paper, school_centre: str = "") -> None:
        from accounts.models import Topic
        text = f"{paper.title} {paper.abstract} {school_centre}".lower()
        topic_map = {
            "Indian Knowledge Systems (IKS)": ["iks", "indian knowledge", "astronomical", "vedic", "mahabharata", "sanskrit", "kautilya", "dharma", "avadhana", "indic"],
            "Biosciences & Genomics": ["bioscience", "biotechnology", "protein", "drug delivery", "amphiphiles", "cell", "mitochondrial", "varicose", "plant", "stress tolerance", "biological", "disease biology", "bioengineering"],
            "Genomics & Bioinformatics": ["genomics", "bioinformatics", "genome", "transcriptome", "qtl", "kelch", "proteome", "sequence and ai"],
            "Management & Financial Analytics": ["management", "profitability", "financial", "telecommunication", "mutual fund", "commerce", "nav", "equity", "debt", "market"],
            "Public Policy & Governance": ["policy", "governance", "international relations", "geopolitics", "security", "defence", "foreign", "ministry"],
            "Artificial Intelligence & NLP": ["artificial intelligence", "machine learning", "deep learning", "neural", "nlp", "language model"],
            "Computational Mathematics": ["mathematics", "computing", "algorithm", "graph", "spectral", "numerical"],
            "Cognitive Psychology": ["psychology", "consciousness", "attention", "cognitive"],
            "Sustainable Development & Clean Energy": ["sustainability", "forest", "ecology", "landscape", "environmental", "clean energy"],
        }
        matched = []
        for topic_name, kws in topic_map.items():
            if any(k in text for k in kws):
                t = Topic.objects.filter(name__iexact=topic_name).first()
                if t:
                    matched.append(t)
        if not matched:
            fallback = Topic.objects.filter(name__icontains="Artificial Intelligence").first() or Topic.objects.first()
            if fallback:
                matched.append(fallback)
        paper.topics.add(*matched)

    @classmethod
    def find_existing_paper(cls, doi: Optional[str], title: str, abstract: str = "") -> Optional[Paper]:
        if doi:
            clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
            existing = Paper.objects.filter(canonical_doi__iexact=clean_doi).first()
            if existing:
                return existing

        norm_title = cls._normalize_title(title)
        if norm_title:
            for p in Paper.objects.only("id", "title", "canonical_doi", "sources"):
                p_norm = cls._normalize_title(p.title)
                if p_norm == norm_title:
                    return p

        try:
            from unified_search.services import EntityResolver
            paper_mh = EntityResolver._create_minhash(f"{title} {abstract}")
            words = [w for w in title.lower().split() if len(w) > 4][:5]
            if words:
                from django.db.models import Q
                q = Q()
                for w in words:
                    q |= Q(title__icontains=w)
                candidates = Paper.objects.filter(q)[:20]
                for cand in candidates:
                    cand_mh = EntityResolver._create_minhash(f"{cand.title} {cand.abstract}")
                    if paper_mh.jaccard(cand_mh) >= 0.40:
                        return cand
        except Exception:
            pass

        return None

    @classmethod
    def ingest(cls, faculty_limit: int = 50, batch_size: int = 300) -> Dict[str, Any]:
        """
        Executes full ELT ingestion for Chanakya University publications:
        1. Extract & Lakehouse Archival (data/ + MinIO)
        2. Deduplication (DOI + Normalized Title + MinHash LSH)
        3. Transform: 384-d embeddings + PaperChunks
        4. Shared Library (ResearchResource + SavedResearchItem) & Topic Linkage
        5. Citation PageRank & Star-Schema Parquet re-export
        """
        from institutional_analytics.services import StarSchemaETLService

        publications = cls.fetch_all_publications(faculty_limit=faculty_limit)
        if batch_size and batch_size > 0:
            publications = publications[:batch_size]

        created_count = 0
        deduped_count = 0

        for item in publications:
            title = item["title"]
            doi = item.get("doi")
            abstract = item.get("abstract", "")
            authors = item.get("authors", [])
            school_centre = item.get("school_centre", "")

            existing_paper = cls.find_existing_paper(doi=doi, title=title, abstract=abstract)

            if existing_paper is not None:
                # Deduplication: merge sources without creating duplicate row
                updated_sources = set(existing_paper.sources or [])
                updated_sources.add("chanakya_university")
                existing_paper.sources = sorted(list(updated_sources))
                if not existing_paper.abstract and abstract:
                    existing_paper.abstract = abstract
                if not existing_paper.venue and item.get("venue"):
                    existing_paper.venue = (item.get("venue") or "")[:255]
                existing_paper.save(update_fields=["sources", "abstract", "venue", "updated_at"])
                cls.link_faculty_publication(existing_paper, authors, school_centre)
                cls.assign_topics(existing_paper, school_centre)
                deduped_count += 1
            else:
                # Brand new paper
                text_for_embedding = f"{title}\n{abstract}".strip()
                emb = EmbeddingService.generate_embedding(text_for_embedding)

                safe_doi = (doi[:255] if doi else None)
                safe_url = (item.get("url") or "")[:500]
                safe_venue = (item.get("venue") or "")[:255]

                new_paper = Paper.objects.create(
                    canonical_doi=safe_doi,
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    published_year=item.get("published_year"),
                    venue=safe_venue,
                    url=safe_url,
                    sources=["chanakya_university"],
                    embedding=emb,
                    pagerank_score=0.015,
                )

                # Generate PaperChunks for RAG Q&A (F8)
                content_to_chunk = f"{title}\n\n{abstract}"
                chunks = TextChunker.chunk_text(content_to_chunk, chunk_size_words=120, overlap_words=25)
                chunk_embeddings = EmbeddingService.generate_batch(chunks)
                chunk_objs = [
                    PaperChunk(paper=new_paper, chunk_index=idx, chunk_text=ct, embedding=ce)
                    for idx, (ct, ce) in enumerate(zip(chunks, chunk_embeddings))
                ]
                PaperChunk.objects.bulk_create(chunk_objs)

                cls.link_faculty_publication(new_paper, authors, school_centre)
                cls.assign_topics(new_paper, school_centre)
                created_count += 1

        # Recompute citation graph PageRank
        IngestionPipeline.recompute_pagerank()

        # Re-export papers.parquet
        IngestionPipeline.export_papers_parquet()

        # Refresh Star Schema Parquet tables for F9 Institutional Analytics
        try:
            StarSchemaETLService.run_etl()
        except Exception as e:
            logger.warning(f"StarSchemaETLService execution error: {e}")

        from research_library.models import ResearchResource
        stats = {
            "created": created_count,
            "deduplicated": deduped_count,
            "total_processed": len(publications),
            "total_papers": Paper.objects.count(),
            "total_chunks": PaperChunk.objects.count(),
            "total_library_items": ResearchResource.objects.count(),
        }
        return stats


# =====================================================================
# 4. Content Ingestion Pipeline & Incremental Refresh
# =====================================================================

class IngestionPipeline:
    """Transforms, deduplicates, generates embeddings/chunks, and persists normalized papers."""

    @classmethod
    @transaction.atomic
    def save_paper_record(cls, data: Dict[str, Any], default_user: Optional[Any] = None) -> Tuple[Paper, bool]:
        """
        Incrementally saves a paper record.
        If paper already exists by DOI, arXiv ID, or OpenAlex ID, merges sources and skips re-embedding.
        """
        doi = data.get("canonical_doi")
        arxiv_id = data.get("arxiv_id")
        openalex_id = data.get("openalex_id")
        title = data.get("title", "").strip()

        paper = None
        # Incremental check: matching by DOI, arxiv_id, or openalex_id
        if doi:
            paper = Paper.objects.filter(canonical_doi__iexact=doi).first()
        if not paper and arxiv_id:
            paper = Paper.objects.filter(arxiv_id__iexact=arxiv_id).first()
        if not paper and openalex_id:
            paper = Paper.objects.filter(openalex_id__iexact=openalex_id).first()

        created = False
        if paper is not None:
            # Paper already exists: merge sources without re-generating embeddings
            updated_sources = set(paper.sources or [])
            for s in data.get("sources", []):
                updated_sources.add(s)
            paper.sources = sorted(list(updated_sources))
            if not paper.abstract and data.get("abstract"):
                paper.abstract = data.get("abstract")
            if not paper.venue and data.get("venue"):
                paper.venue = data.get("venue")
            paper.save(update_fields=["sources", "abstract", "venue", "updated_at"])
            return paper, False

        # Brand new paper: generate embeddings and chunks
        text_for_embedding = f"{title}\n{data.get('abstract', '')}".strip()
        embedding = EmbeddingService.generate_embedding(text_for_embedding)

        paper = Paper.objects.create(
            canonical_doi=doi,
            arxiv_id=arxiv_id,
            openalex_id=openalex_id,
            title=title,
            authors=data.get("authors", []),
            abstract=data.get("abstract", ""),
            published_year=data.get("published_year"),
            venue=data.get("venue", ""),
            url=data.get("url", ""),
            sources=data.get("sources", ["external"]),
            embedding=embedding,
            pagerank_score=0.01,
        )
        created = True

        # Generate text chunks for RAG Assistant (F8)
        content_to_chunk = f"{title}\n\n{paper.abstract}"
        chunks = TextChunker.chunk_text(content_to_chunk, chunk_size_words=120, overlap_words=25)
        chunk_embeddings = EmbeddingService.generate_batch(chunks)

        chunk_objs = []
        for idx, (chunk_text, chunk_emb) in enumerate(zip(chunks, chunk_embeddings)):
            chunk_objs.append(
                PaperChunk(
                    paper=paper,
                    chunk_index=idx,
                    chunk_text=chunk_text,
                    embedding=chunk_emb,
                )
            )
        PaperChunk.objects.bulk_create(chunk_objs)

        # Bridge with research_library.ResearchResource cleanly
        cls._link_research_resource(paper, default_user)

        return paper, True

    @classmethod
    def _link_research_resource(cls, paper: Paper, default_user: Optional[Any] = None) -> Optional[ResearchResource]:
        """Creates or links a ResearchResource in research_library so the paper is in the shared library."""
        try:
            user = default_user or User.objects.filter(is_staff=True).first() or User.objects.first()
            if not user:
                return None

            resource = None
            if paper.canonical_doi:
                resource = ResearchResource.objects.filter(doi__iexact=paper.canonical_doi).first()
            if not resource and paper.arxiv_id:
                resource = ResearchResource.objects.filter(arxiv_id__iexact=paper.arxiv_id).first()

            if resource is None:
                res_url = paper.url or (f"https://doi.org/{paper.canonical_doi}" if paper.canonical_doi else (f"https://arxiv.org/abs/{paper.arxiv_id}" if paper.arxiv_id else ""))
                resource = ResearchResource.objects.create(
                    title=paper.title[:250],
                    description=paper.abstract[:500] if paper.abstract else f"Scholarly publication by {paper.authors_display}",
                    resource_type="link",
                    url=res_url[:200] if res_url else "https://chanakyauniversity.edu.in",
                    doi=paper.canonical_doi[:255] if paper.canonical_doi else None,
                    arxiv_id=paper.arxiv_id[:100] if paper.arxiv_id else None,
                    uploaded_by=user,
                )
            paper.resource = resource
            paper.save(update_fields=["resource"])
            return resource
        except Exception as e:
            logger.warning(f"Could not link ResearchResource for paper {paper.id}: {e}")
            return None

    @classmethod
    def run_ingestion(cls, source: str = "all", query: str = "computer science", limit: int = 25) -> Dict[str, int]:
        """Orchestrates ingestion across OpenAlex, arXiv, and RSS feeds."""
        records: List[Dict[str, Any]] = []

        if source in ("openalex", "all"):
            records.extend(OpenAlexIngester.fetch(query=query, limit=limit))

        if source in ("arxiv", "all"):
            records.extend(ArxivIngester.fetch(query=query, limit=limit))

        if source in ("rss", "all"):
            records.extend(RSSIngester.fetch(limit=limit))

        created_count = 0
        updated_count = 0

        for r in records:
            _, created = cls.save_paper_record(r)
            if created:
                created_count += 1
            else:
                updated_count += 1

        # Recompute citation graph PageRank after new batch
        cls.recompute_pagerank()

        # Export updated dataset to MinIO Parquet
        cls.export_papers_parquet()

        return {"created": created_count, "updated": updated_count, "total_processed": len(records)}

    @classmethod
    def recompute_pagerank(cls) -> int:
        """Constructs a NetworkX DiGraph of citation links and recalculates PageRank scores."""
        G = nx.DiGraph()

        # Add all paper nodes
        all_paper_ids = list(Paper.objects.values_list("id", flat=True))
        for pid in all_paper_ids:
            G.add_node(pid)

        # Add citation edges
        citations = PaperCitation.objects.values_list("citing_paper_id", "cited_paper_id")
        for citing, cited in citations:
            if G.has_node(citing) and G.has_node(cited):
                G.add_edge(citing, cited)

        if not G.nodes():
            return 0

        # Calculate PageRank
        try:
            scores = nx.pagerank(G, alpha=0.85, max_iter=100)
        except Exception as e:
            logger.warning(f"PageRank computation defaulted: {e}")
            scores = {n: 1.0 / len(G.nodes()) for n in G.nodes()}

        # Bulk update papers
        updated_papers = []
        for paper in Paper.objects.all():
            new_score = scores.get(paper.id, 0.001)
            paper.pagerank_score = round(float(new_score), 6)
            updated_papers.append(paper)

        Paper.objects.bulk_update(updated_papers, ["pagerank_score"])
        return len(updated_papers)

    @classmethod
    def export_papers_parquet(cls) -> str:
        """Exports normalized Paper records into a Parquet table and stores it in MinIO."""
        papers = Paper.objects.all().values(
            "id", "canonical_doi", "arxiv_id", "openalex_id", "title",
            "published_year", "venue", "url", "pagerank_score", "save_count", "created_at"
        )
        if not papers:
            return ""

        table = pa.Table.from_pylist(list(papers))
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="snappy")
        parquet_bytes = buf.getvalue()

        # Upload to MinIO and local directory
        object_name = "papers/papers.parquet"
        return MinIOService.upload_parquet(object_name, parquet_bytes)


# =====================================================================
# 6. Scheduled Batch Ingestion Service (F4)
# =====================================================================

class ScheduledIngestionService:
    """
    Automates incremental scheduled batch ingestion across scholarly sources.
    Features:
    - Topic watermark rotation across university departments.
    - Idempotent incremental saving (reuses existing DOIs/arXiv IDs).
    - Error isolation and run logging in IngestionRunLog.
    - Admin inspection reporting.
    """

    ROTATING_TOPICS = [
        "quantum computing",
        "deep learning",
        "transformer architectures",
        "genomics bioinformatics",
        "renewable energy storage",
        "reinforcement learning",
        "computational neuroscience",
        "natural language processing",
    ]

    @classmethod
    def execute_scheduled_batch(
        cls, source: str = "all", topic: Optional[str] = None, batch_limit: int = 15
    ) -> Any:
        """Executes a single scheduled batch run, logs the status, and returns the run log."""
        from .models import IngestionRunLog

        # Determine topic watermark
        if not topic:
            last_run = IngestionRunLog.objects.filter(status="success").order_by("-started_at").first()
            last_watermark = last_run.watermark if last_run else ""
            try:
                next_idx = (cls.ROTATING_TOPICS.index(last_watermark) + 1) % len(cls.ROTATING_TOPICS)
                topic = cls.ROTATING_TOPICS[next_idx]
            except ValueError:
                topic = cls.ROTATING_TOPICS[0]

        run_log = IngestionRunLog.objects.create(
            source=source,
            status="running",
            watermark=topic,
            details={"batch_limit": batch_limit, "target_topic": topic},
        )

        try:
            logger.info(f"Executing scheduled batch ingestion for '{topic}' from '{source}'")
            records: List[Dict[str, Any]] = []

            # 1. Fetch from sources with error isolation
            if source in ("openalex", "all"):
                try:
                    records.extend(OpenAlexIngester.fetch(query=topic, limit=batch_limit // 2 or 10))
                except Exception as e:
                    logger.error(f"OpenAlex scheduled fetch failed: {e}")

            if source in ("arxiv", "all"):
                try:
                    records.extend(ArxivIngester.fetch(query=topic, limit=batch_limit // 2 or 10))
                except Exception as e:
                    logger.error(f"arXiv scheduled fetch failed: {e}")

            if source in ("rss", "all"):
                try:
                    records.extend(RSSIngester.fetch(limit=5))
                except Exception as e:
                    logger.error(f"RSS scheduled fetch failed: {e}")

            run_log.records_fetched = len(records)

            # 2. Incrementally persist
            created = 0
            updated = 0
            for r in records:
                try:
                    _, is_created = IngestionPipeline.save_paper_record(r)
                    if is_created:
                        created += 1
                    else:
                        updated += 1
                except Exception as e:
                    logger.warning(f"Error persisting paper record: {e}")

            run_log.records_created = created
            run_log.records_updated = updated
            run_log.status = "success"
            run_log.completed_at = timezone.now()
            run_log.save()
            return run_log

        except Exception as e:
            run_log.status = "failed"
            run_log.error_message = str(e)
            run_log.completed_at = timezone.now()
            run_log.save()
            return run_log


