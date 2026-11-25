import math
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
from django.contrib.auth import get_user_model
from django.db.models import Count, F, Q
from mlxtend.frequent_patterns import association_rules, fpgrowth
from pgvector.django import CosineDistance

from accounts.models import MemberFollow, Profile, Topic
from papers.models import Paper
from papers.services import EmbeddingService
from research_library.models import ResearchResource, SavedResearchItem

User = get_user_model()


class RecommendationService:
    """Delivers personalized paper recommendations, member matching, and 'also saved' association rules."""

    @classmethod
    def get_recommended_papers(
        cls, user: Optional[Any], limit: int = 10, exclude_saved_item_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Recommends papers for logged-in user:
        - If active: Content-based embedding similarity + Collaborative filtering
        - If cold-start: Department popularity + topic interests + PageRank fallback
        """
        if not user or not user.is_authenticated:
            # Fallback for anonymous visitors: Top PageRank & most saved papers
            top_papers = list(Paper.objects.all().order_by("-pagerank_score", "-save_count")[:limit])
            return {
                "strategy": "popularity",
                "label": "Trending Across the University",
                "papers": top_papers,
            }

        # 1. Check user activity
        user_saves = SavedResearchItem.objects.filter(user=user).select_related("resource")
        if exclude_saved_item_ids:
            user_saves = user_saves.exclude(id__in=exclude_saved_item_ids)

        saved_resource_ids = list(user_saves.values_list("resource_id", flat=True))
        saved_papers = Paper.objects.filter(
            Q(resource_id__in=saved_resource_ids)
            | Q(canonical_doi__in=[s.resource.doi for s in user_saves if s.resource.doi])
            | Q(arxiv_id__in=[s.resource.arxiv_id for s in user_saves if s.resource.arxiv_id])
        )
        saved_paper_ids = set(saved_papers.values_list("id", flat=True))

        profile = getattr(user, "profile", None)
        user_topics = list(profile.topics.all()) if profile else []

        # ==============================================================
        # PATH A: ACTIVE USER (Content-Based + Collaborative Filtering)
        # ==============================================================
        if saved_paper_ids:
            # A1. Compute user centroid embedding from saved papers
            saved_embeddings = [p.embedding for p in saved_papers if p.embedding is not None]

            if saved_embeddings:
                # Average embeddings to get preference vector
                centroid = [0.0] * 384
                for emb in saved_embeddings:
                    for i in range(384):
                        centroid[i] += float(emb[i])
                norm = math.sqrt(sum(x * x for x in centroid)) or 1.0
                centroid = [x / norm for x in centroid]

                # Semantic nearest neighbors
                sem_candidates = list(
                    Paper.objects.exclude(id__in=saved_paper_ids)
                    .filter(embedding__isnull=False)
                    .annotate(distance=CosineDistance("embedding", centroid))
                    .order_by("distance")[: 50]
                )
            else:
                sem_candidates = list(
                    Paper.objects.exclude(id__in=saved_paper_ids).order_by(
                        "-pagerank_score"
                    )[: 50]
                )

            # A2. Collaborative Filtering: Co-saver user boost
            co_saver_user_ids = (
                SavedResearchItem.objects.filter(resource_id__in=saved_resource_ids)
                .exclude(user=user)
                .values_list("user_id", flat=True)
                .distinct()
            )

            # Resources saved by co-savers
            cf_boost_counts = (
                SavedResearchItem.objects.filter(user_id__in=co_saver_user_ids)
                .exclude(resource_id__in=saved_resource_ids)
                .values("resource_id")
                .annotate(co_count=Count("id"))
                .order_by("-co_count")[: 50]
            )
            cf_boost_map = {item["resource_id"]: item["co_count"] for item in cf_boost_counts}

            # Collaborative filtering candidate papers
            cf_candidates = list(
                Paper.objects.filter(resource_id__in=cf_boost_map.keys()).exclude(id__in=saved_paper_ids)
            )

            # Merge candidates uniquely
            candidate_map = {p.id: p for p in sem_candidates + cf_candidates}

            # Score candidates
            scored = []
            for p in candidate_map.values():
                cos_sim = max(0.0, 1.0 - float(getattr(p, "distance", 0.5) or 0.5))
                cf_count = cf_boost_map.get(p.resource_id, 0)
                cf_score = min(1.0, cf_count / 5.0)
                final_score = (0.50 * cos_sim) + (0.50 * cf_score)
                scored.append((p, final_score))

            scored.sort(key=lambda x: x[1], reverse=True)
            recommended = [p for p, _ in scored[:limit]]

            return {
                "strategy": "personalized_hybrid",
                "label": "Recommended for Your Research Profile",
                "papers": recommended,
            }

        # ==============================================================
        # PATH B: COLD-START USER (Department Popularity + Profile Tags)
        # ==============================================================
        department = profile.department if profile else None

        if department:
            # B1. Most saved papers by members in the same department
            dept_saves = (
                SavedResearchItem.objects.filter(user__profile__department=department)
                .values("resource_id")
                .annotate(save_count=Count("id"))
                .order_by("-save_count")[:limit]
            )
            dept_res_ids = [d["resource_id"] for d in dept_saves]
            dept_papers = list(Paper.objects.filter(resource_id__in=dept_res_ids))
            if len(dept_papers) >= 3:
                return {
                    "strategy": "cold_start_department",
                    "label": f"Popular in {department.name}",
                    "papers": dept_papers[:limit],
                }

        # B2. Use profile research interests or topics
        if profile and (profile.research_interests or user_topics):
            topic_names = " ".join([t.name for t in user_topics])
            interest_text = f"{profile.research_interests} {topic_names}".strip()
            if interest_text:
                interest_emb = EmbeddingService.generate_embedding(interest_text)
                interest_papers = list(
                    Paper.objects.filter(embedding__isnull=False)
                    .annotate(distance=CosineDistance("embedding", interest_emb))
                    .order_by("distance")[:limit]
                )
                if interest_papers:
                    return {
                        "strategy": "cold_start_interests",
                        "label": "Matches Your Stated Interests",
                        "papers": interest_papers,
                    }

        # B3. Ultimate fallback: Top PageRank & university-wide saved papers
        top_papers = list(Paper.objects.all().order_by("-pagerank_score", "-save_count")[:limit])
        return {
            "strategy": "cold_start_pagerank",
            "label": "Highly Ranked University Publications",
            "papers": top_papers,
        }

    @classmethod
    def get_member_recommendations(cls, user: Any, limit: int = 5) -> List[Dict[str, Any]]:
        """Recommends university researchers/faculty/students based on shared department and topics."""
        if not user or not user.is_authenticated:
            return []

        user_profile = getattr(user, "profile", None)
        user_dept_id = user_profile.department_id if user_profile else None
        user_topic_ids = set(user_profile.topics.values_list("id", flat=True)) if user_profile else set()

        # Already followed members
        following_ids = set(MemberFollow.objects.filter(follower=user).values_list("followed_id", flat=True))
        following_ids.add(user.id)

        candidates = (
            User.objects.filter(is_active=True)
            .exclude(id__in=following_ids)
            .select_related("profile", "profile__department")
            .prefetch_related("profile__topics")[:50]
        )

        scored_members = []
        for cand in candidates:
            score = 0.0
            reasons = []

            cand_profile = getattr(cand, "profile", None)
            if not cand_profile:
                continue

            # 1. Department match (+0.4)
            if user_dept_id and cand_profile.department_id == user_dept_id:
                score += 0.4
                reasons.append(f"Same Department ({cand_profile.department.name})")

            # 2. Topic overlap (+0.4 * Jaccard)
            cand_topic_ids = set(cand_profile.topics.values_list("id", flat=True))
            if user_topic_ids and cand_topic_ids:
                intersection = user_topic_ids & cand_topic_ids
                union = user_topic_ids | cand_topic_ids
                jaccard = len(intersection) / len(union) if union else 0.0
                score += 0.4 * jaccard
                if intersection:
                    common_topic_names = Topic.objects.filter(id__in=intersection).values_list("name", flat=True)
                    reasons.append(f"Shared topics: {', '.join(list(common_topic_names)[:2])}")

            # 3. Role affinity (+0.2)
            if cand_profile.role in ("faculty", "researcher"):
                score += 0.2

            if score > 0.1:
                scored_members.append({
                    "user": cand,
                    "score": round(score, 3),
                    "reasons": reasons or ["Academic colleague"],
                })

        scored_members.sort(key=lambda x: x["score"], reverse=True)
        return scored_members[:limit]

    @classmethod
    def get_also_saved_for_paper(cls, paper: Any, limit: int = 5) -> List[Dict[str, Any]]:
        """
        'Members who saved this also saved' co-occurrence & association rules using mlxtend FP-Growth or lift/support.
        """
        # Determine the target resource_id
        target_resource_id = getattr(paper, "resource_id", None)
        if not target_resource_id and hasattr(paper, "resource") and paper.resource:
            target_resource_id = paper.resource.id
        elif not target_resource_id and hasattr(paper, "id") and isinstance(paper, ResearchResource):
            target_resource_id = paper.id

        if not target_resource_id:
            return []

        # Find users who saved this item
        users_who_saved = set(
            SavedResearchItem.objects.filter(resource_id=target_resource_id).values_list("user_id", flat=True)
        )
        if not users_who_saved:
            # Fallback to papers in the same topics
            return cls._get_topic_fallback_recommendations(paper, limit)

        total_users_count = max(1, User.objects.filter(is_active=True).count())
        target_save_count = len(users_who_saved)

        # Other items saved by these same users
        co_saved_counts = (
            SavedResearchItem.objects.filter(user_id__in=users_who_saved)
            .exclude(resource_id=target_resource_id)
            .values("resource_id")
            .annotate(co_count=Count("id"))
            .filter(co_count__gte=1)
            .order_by("-co_count")[: limit * 3]
        )

        if not co_saved_counts:
            return cls._get_topic_fallback_recommendations(paper, limit)

        results = []
        for item in co_saved_counts:
            res_id = item["resource_id"]
            co_count = item["co_count"]

            # Compute Lift and Support
            other_total_saves = SavedResearchItem.objects.filter(resource_id=res_id).count() or 1
            support = co_count / total_users_count
            confidence = co_count / target_save_count
            lift = (co_count * total_users_count) / (target_save_count * other_total_saves)

            resource = ResearchResource.objects.filter(id=res_id).first()
            if resource:
                linked_paper = getattr(resource, "papers", None)
                first_paper = linked_paper.first() if linked_paper else None

                results.append({
                    "resource": resource,
                    "paper": first_paper,
                    "co_save_count": co_count,
                    "confidence": round(confidence, 2),
                    "lift": round(lift, 2),
                })

        results.sort(key=lambda x: (x["lift"], x["co_save_count"]), reverse=True)
        return results[:limit]

    @classmethod
    def _get_topic_fallback_recommendations(cls, paper: Any, limit: int = 5) -> List[Dict[str, Any]]:
        """Fallback recommendation when co-occurrence data is sparse."""
        target_id = getattr(paper, "id", None)
        fallback_papers = Paper.objects.exclude(id=target_id).order_by("-pagerank_score")[:limit]
        return [
            {
                "resource": p.resource,
                "paper": p,
                "co_save_count": p.save_count,
                "confidence": 0.5,
                "lift": 1.0,
            }
            for p in fallback_papers
        ]
