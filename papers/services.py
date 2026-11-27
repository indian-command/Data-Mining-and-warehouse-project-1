import io
import json
import logging
import re
import urllib.parse
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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
                resource = ResearchResource.objects.create(
                    title=paper.title,
                    description=paper.abstract[:500] if paper.abstract else f"Scholarly publication by {paper.authors_display}",
                    resource_type="link",
                    url=paper.url or (f"https://doi.org/{paper.canonical_doi}" if paper.canonical_doi else f"https://arxiv.org/abs/{paper.arxiv_id}"),
                    doi=paper.canonical_doi,
                    arxiv_id=paper.arxiv_id,
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


