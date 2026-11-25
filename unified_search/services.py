import re
from typing import Any, Dict, List, Optional, Set

from datasketch import MinHash, MinHashLSH
from django.contrib.auth import get_user_model
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Count, F, Q
from pgvector.django import CosineDistance

from accounts.models import Profile, Topic
from discussions.models import DiscussionPost
from papers.models import Paper
from papers.services import EmbeddingService
from research_library.models import ResearchResource
from trends.services import EventLogger

User = get_user_model()


# =====================================================================
# 1. Deduplication & Entity Resolution via MinHash / LSH (datasketch)
# =====================================================================

class EntityResolver:
    """Merges cross-source duplicates across OpenAlex, arXiv, and Library using DOI/arXiv & MinHash LSH."""

    @staticmethod
    def _create_minhash(text: str, num_perm: int = 128) -> MinHash:
        m = MinHash(num_perm=num_perm)
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", text.lower())
        words = cleaned.split()
        shingles = set(words)
        # Word 2-grams
        for i in range(len(words) - 1):
            shingles.add(f"{words[i]}_{words[i+1]}")
        # Substring character 3-grams
        for w in words:
            if len(w) >= 3:
                for j in range(len(w) - 2):
                    shingles.add(w[j : j + 3])
        for s in shingles:
            m.update(s.encode("utf-8"))
        return m

    @classmethod
    def resolve_and_deduplicate(cls, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicates candidate papers using:
        1. Exact DOI match
        2. Exact arXiv ID match
        3. Normalized Title match
        4. MinHash LSH on Title + Abstract (threshold 0.60)
        Returns unified records with merged source badges.
        """
        if not papers:
            return []

        lsh = MinHashLSH(threshold=0.60, num_perm=128)
        clusters: List[Dict[str, Any]] = []
        cluster_minhashes: List[MinHash] = []

        # Index clusters by DOI, arXiv ID, and Normalized Title
        doi_to_cluster_idx: Dict[str, int] = {}
        arxiv_to_cluster_idx: Dict[str, int] = {}
        norm_title_to_cluster_idx: Dict[str, int] = {}

        for paper in papers:
            doi = paper.get("canonical_doi")
            if doi:
                doi = doi.lower().strip()
            arxiv_id = paper.get("arxiv_id")
            if arxiv_id:
                arxiv_id = arxiv_id.lower().strip()

            raw_title = paper.get("title", "")
            # Clean parentheticals like (Conference Proceedings), [Preprint], etc. for entity resolution
            clean_title = re.sub(r"\(.*?\)|\[.*?\]", "", raw_title)
            norm_title = re.sub(r"[^a-zA-Z0-9]", "", clean_title.lower())

            target_cluster_idx: Optional[int] = None

            # 1. Exact DOI match
            if doi and doi in doi_to_cluster_idx:
                target_cluster_idx = doi_to_cluster_idx[doi]

            # 2. Exact arXiv ID match
            if target_cluster_idx is None and arxiv_id and arxiv_id in arxiv_to_cluster_idx:
                target_cluster_idx = arxiv_to_cluster_idx[arxiv_id]

            # 3. Normalized Title exact match
            if target_cluster_idx is None and norm_title and norm_title in norm_title_to_cluster_idx:
                target_cluster_idx = norm_title_to_cluster_idx[norm_title]

            # 4. MinHash LSH near-duplicate match
            paper_text = f"{raw_title} {paper.get('abstract', '')}"
            paper_mh = cls._create_minhash(paper_text)

            if target_cluster_idx is None:
                matches = lsh.query(paper_mh)
                if matches:
                    target_cluster_idx = int(matches[0].replace("cluster_", ""))

            if target_cluster_idx is not None and target_cluster_idx < len(clusters):
                # Merge into existing cluster
                target = clusters[target_cluster_idx]
                target["sources"] = sorted(list(set(target.get("sources", []) + paper.get("sources", []))))
                target["cluster_ids"] = target.get("cluster_ids", [target["id"]]) + [paper["id"]]
                if not target.get("canonical_doi") and doi:
                    target["canonical_doi"] = doi
                    doi_to_cluster_idx[doi] = target_cluster_idx
                if not target.get("arxiv_id") and arxiv_id:
                    target["arxiv_id"] = arxiv_id
                    arxiv_to_cluster_idx[arxiv_id] = target_cluster_idx
                if len(paper.get("abstract", "")) > len(target.get("abstract", "")):
                    target["abstract"] = paper["abstract"]
                if paper.get("pagerank_score", 0.0) > target.get("pagerank_score", 0.0):
                    target["pagerank_score"] = paper["pagerank_score"]
                if paper.get("score", 0.0) > target.get("score", 0.0):
                    target["score"] = paper["score"]
            else:
                # Create a new cluster
                new_idx = len(clusters)
                paper_copy = dict(paper)
                paper_copy["sources"] = sorted(list(set(paper_copy.get("sources", []))))
                paper_copy["cluster_ids"] = [paper_copy["id"]]
                clusters.append(paper_copy)
                cluster_minhashes.append(paper_mh)

                cluster_key = f"cluster_{new_idx}"
                lsh.insert(cluster_key, paper_mh)

                if doi:
                    doi_to_cluster_idx[doi] = new_idx
                if arxiv_id:
                    arxiv_to_cluster_idx[arxiv_id] = new_idx
                if norm_title:
                    norm_title_to_cluster_idx[norm_title] = new_idx

        # Return sorted by score
        return sorted(clusters, key=lambda x: x.get("score", 0.0), reverse=True)


# =====================================================================
# 2. 4-Panel Hybrid Unified Search Service
# =====================================================================

class UnifiedSearchService:
    """Executes 4-panel hybrid search: Scholarly Sources, Library, Members, and Discussions."""

    @classmethod
    def search_scholarly_sources(cls, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Hybrid Keyword + pgvector Cosine + PageRank Search over Papers with Deduplication."""
        if not query.strip():
            # Return top PageRank papers if no query
            papers = Paper.objects.all().order_by("-pagerank_score")[:limit]
            candidates = [cls._paper_to_dict(p, score=p.pagerank_score) for p in papers]
            return EntityResolver.resolve_and_deduplicate(candidates)

        query_emb = EmbeddingService.generate_embedding(query)

        # 1. Semantic vector search using pgvector CosineDistance
        vector_results = (
            Paper.objects.filter(embedding__isnull=False)
            .annotate(distance=CosineDistance("embedding", query_emb))
            .order_by("distance")[: limit * 2]
        )

        vector_scores = {}
        for p in vector_results:
            sim = max(0.0, 1.0 - float(p.distance or 1.0))
            vector_scores[p.id] = (p, sim)

        # 2. Full-text keyword search
        search_query = SearchQuery(query, config="english")
        search_vector = SearchVector("title", weight="A") + SearchVector("abstract", weight="B")
        keyword_results = (
            Paper.objects.annotate(rank=SearchRank(search_vector, search_query))
            .filter(Q(rank__gte=0.01) | Q(title__icontains=query) | Q(abstract__icontains=query))
            .order_by("-rank")[: limit * 2]
        )

        keyword_scores = {}
        for p in keyword_results:
            rank = getattr(p, "rank", 0.1) or 0.1
            keyword_scores[p.id] = (p, float(rank))

        # 3. Combine scores into Hybrid Score
        all_ids = set(vector_scores.keys()) | set(keyword_scores.keys())
        if not all_ids:
            # Fallback simple substring search
            fallback = Paper.objects.filter(
                Q(title__icontains=query) | Q(abstract__icontains=query)
            )[:limit]
            candidates = [cls._paper_to_dict(p, score=0.5) for p in fallback]
            return EntityResolver.resolve_and_deduplicate(candidates)

        combined = []
        for pid in all_ids:
            paper_obj = None
            v_score = 0.0
            k_score = 0.0

            if pid in vector_scores:
                paper_obj, v_score = vector_scores[pid]
            if pid in keyword_scores:
                paper_obj, k_score = keyword_scores[pid]

            if paper_obj is None:
                continue

            pr_score = float(paper_obj.pagerank_score or 0.0)
            # Weighted Hybrid Score: 0.40 Keyword + 0.45 Vector + 0.15 PageRank
            hybrid_score = (0.40 * min(1.0, k_score * 2.0)) + (0.45 * v_score) + (0.15 * min(1.0, pr_score * 10.0))
            combined.append(cls._paper_to_dict(paper_obj, score=round(hybrid_score, 4)))

        # 4. Deduplication & Entity Resolution
        return EntityResolver.resolve_and_deduplicate(combined)[:limit]

    @classmethod
    def search_library_resources(cls, query: str, limit: int = 10) -> List[ResearchResource]:
        """Searches shared Chanakya Research Library resources."""
        if not query.strip():
            return list(
                ResearchResource.objects.annotate(member_save_count=Count("saves__user", distinct=True))
                .order_by("-member_save_count")[:limit]
            )

        return list(
            ResearchResource.objects.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(doi__icontains=query)
                | Q(arxiv_id__icontains=query)
            )
            .annotate(member_save_count=Count("saves__user", distinct=True))
            .order_by("-member_save_count", "-created_at")[:limit]
        )

    @classmethod
    def search_university_members(cls, query: str, limit: int = 10) -> List[Any]:
        """Searches students, faculty, and researchers across departments."""
        if not query.strip():
            return list(
                User.objects.filter(is_active=True)
                .select_related("profile", "profile__department")
                .order_by("-date_joined")[:limit]
            )

        return list(
            User.objects.filter(is_active=True)
            .filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(profile__bio__icontains=query)
                | Q(profile__research_interests__icontains=query)
                | Q(profile__department__name__icontains=query)
                | Q(profile__topics__name__icontains=query)
            )
            .select_related("profile", "profile__department")
            .distinct()[:limit]
        )

    @classmethod
    def search_discussions(cls, query: str, limit: int = 10) -> List[DiscussionPost]:
        """Searches discussion posts, tags, and attached resources."""
        if not query.strip():
            return list(
                DiscussionPost.objects.select_related("author")
                .prefetch_related("tags")
                .order_by("-created_at")[:limit]
            )

        return list(
            DiscussionPost.objects.filter(
                Q(title__icontains=query)
                | Q(content__icontains=query)
                | Q(tags__name__icontains=query)
            )
            .select_related("author")
            .prefetch_related("tags")
            .distinct()
            .order_by("-created_at")[:limit]
        )

    @classmethod
    def execute_unified_search(cls, query: str, user: Optional[Any] = None) -> Dict[str, Any]:
        """Executes all 4 panels in parallel/coordinated sequence and logs search event."""
        clean_query = query.strip()

        # Log event for trends & analytics
        if clean_query:
            EventLogger.log_event(
                user=user,
                event_type="search",
                target_type="query",
                target_id=clean_query[:100],
                metadata={"query": clean_query},
            )

        scholarly = cls.search_scholarly_sources(clean_query, limit=15)
        library = cls.search_library_resources(clean_query, limit=10)
        members = cls.search_university_members(clean_query, limit=10)
        discussions = cls.search_discussions(clean_query, limit=10)

        total_results = len(scholarly) + len(library) + len(members) + len(discussions)

        return {
            "query": clean_query,
            "total_count": total_results,
            "scholarly_sources": scholarly,
            "library_resources": library,
            "university_members": members,
            "discussions": discussions,
        }

    @staticmethod
    def _paper_to_dict(paper: Paper, score: float = 0.0) -> Dict[str, Any]:
        return {
            "id": paper.id,
            "title": paper.title,
            "authors": paper.authors,
            "authors_display": paper.authors_display,
            "abstract": paper.abstract,
            "canonical_doi": paper.canonical_doi,
            "arxiv_id": paper.arxiv_id,
            "openalex_id": paper.openalex_id,
            "published_year": paper.published_year,
            "venue": paper.venue,
            "url": paper.url,
            "sources": paper.sources or ["scholarly"],
            "pagerank_score": paper.pagerank_score,
            "save_count": paper.save_count,
            "score": score,
            "resource_id": paper.resource_id,
        }
