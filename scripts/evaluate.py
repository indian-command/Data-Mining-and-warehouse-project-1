import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

# Ensure Django environment is configured
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from papers.models import Paper, PaperChunk
from papers.services import EmbeddingService
from recommendations.services import RecommendationService
from research_assistant.services import ResearchAssistantService
from research_library.models import SavedResearchItem
from trends.models import ModerationFlag
from trends.services import AnomalyDetector, TrendAnalyzer
from unified_search.services import EntityResolver, UnifiedSearchService

User = get_user_model()


def compute_dcg(relevance_list: List[int], k: int = 10) -> float:
    dcg = 0.0
    for i, rel in enumerate(relevance_list[:k], start=1):
        if rel > 0:
            dcg += (2**rel - 1) / math.log2(i + 1)
    return dcg


def compute_ndcg(retrieved_ids: List[int], ground_truth_ids: Set[int], k: int = 10) -> float:
    rel_list = [1 if pid in ground_truth_ids else 0 for pid in retrieved_ids[:k]]
    dcg = compute_dcg(rel_list, k)
    ideal_rel_list = sorted(rel_list, reverse=True)
    if not any(ideal_rel_list):
        # Perfect ranking if any ground truth exists
        ideal_rel_list = [1] * min(len(ground_truth_ids), k)
    idcg = compute_dcg(ideal_rel_list, k)
    return dcg / idcg if idcg > 0 else 0.0


def run_evaluation_suite():
    print("=" * 80)
    print("CHANAKYA RESEARCH COMMONS: QUANTITATIVE EVALUATION BENCHMARK SUITE")
    print("=" * 80)

    gt_file = BASE_DIR / "data" / "ground_truth.json"
    if not gt_file.exists():
        print(f"Error: {gt_file} not found. Please run 'python scripts/generate_synthetic.py' first.")
        return

    with open(gt_file, "r") as f:
        ground_truth = json.load(f)

    # =========================================================================
    # 1. SEARCH QUALITY BENCHMARK (Hybrid+PageRank vs Keyword-Only Baseline)
    # =========================================================================
    print("\n[BENCHMARK 1] SEARCH RETRIEVAL QUALITY (Hybrid + PageRank vs. Keyword-Only Baseline)")
    print("-" * 80)

    search_queries = ground_truth.get("search_benchmark_queries", [])
    if not search_queries:
        # Fallback query set if empty
        search_queries = [
            {"query": "transformer attention neural machine translation", "expected_top_paper_ids": [1]},
            {"query": "deep residual learning convolutional image recognition", "expected_top_paper_ids": [2]},
            {"query": "protein structure prediction alphafold biological sequences", "expected_top_paper_ids": [11]},
        ]

    hybrid_ndcg_list = []
    hybrid_p5_list = []
    hybrid_p10_list = []
    hybrid_recall_list = []

    keyword_ndcg_list = []
    keyword_p5_list = []
    keyword_p10_list = []
    keyword_recall_list = []

    for item in search_queries:
        q_str = item["query"]
        expected_ids = set(item["expected_top_paper_ids"])

        # Model: Hybrid + PageRank Search
        hybrid_results = UnifiedSearchService.search_scholarly_sources(q_str, limit=10)
        h_ids = [p["id"] for p in hybrid_results]

        h_ndcg = compute_ndcg(h_ids, expected_ids, k=10)
        h_p5 = len(set(h_ids[:5]) & expected_ids) / 5.0
        h_p10 = len(set(h_ids[:10]) & expected_ids) / 10.0
        h_rec = len(set(h_ids[:10]) & expected_ids) / max(1, len(expected_ids))

        hybrid_ndcg_list.append(h_ndcg)
        hybrid_p5_list.append(h_p5)
        hybrid_p10_list.append(h_p10)
        hybrid_recall_list.append(h_rec)

        # Baseline: Pure Keyword Search
        q_terms = q_str.split()
        kw_filter = Q()
        for t in q_terms:
            kw_filter |= Q(title__icontains=t) | Q(abstract__icontains=t)
        kw_results = list(Paper.objects.filter(kw_filter).order_by("-published_year")[:10])
        kw_ids = [p.id for p in kw_results]

        kw_ndcg = compute_ndcg(kw_ids, expected_ids, k=10)
        kw_p5 = len(set(kw_ids[:5]) & expected_ids) / 5.0
        kw_p10 = len(set(kw_ids[:10]) & expected_ids) / 10.0
        kw_rec = len(set(kw_ids[:10]) & expected_ids) / max(1, len(expected_ids))

        keyword_ndcg_list.append(kw_ndcg)
        keyword_p5_list.append(kw_p5)
        keyword_p10_list.append(kw_p10)
        keyword_recall_list.append(kw_rec)

    mean_h_ndcg = sum(hybrid_ndcg_list) / len(hybrid_ndcg_list) if hybrid_ndcg_list else 0.0
    mean_h_p5 = sum(hybrid_p5_list) / len(hybrid_p5_list) if hybrid_p5_list else 0.0
    mean_h_p10 = sum(hybrid_p10_list) / len(hybrid_p10_list) if hybrid_p10_list else 0.0
    mean_h_rec = sum(hybrid_recall_list) / len(hybrid_recall_list) if hybrid_recall_list else 0.0

    mean_k_ndcg = sum(keyword_ndcg_list) / len(keyword_ndcg_list) if keyword_ndcg_list else 0.0
    mean_k_p5 = sum(keyword_p5_list) / len(keyword_p5_list) if keyword_p5_list else 0.0
    mean_k_p10 = sum(keyword_p10_list) / len(keyword_p10_list) if keyword_p10_list else 0.0
    mean_k_rec = sum(keyword_recall_list) / len(keyword_recall_list) if keyword_recall_list else 0.0

    print(f"{'Metric':<20} | {'Keyword Baseline':<18} | {'Hybrid + PageRank':<18} | {'Gain':<10}")
    print("-" * 72)
    print(f"{'Precision@5':<20} | {mean_k_p5:<18.4f} | {mean_h_p5:<18.4f} | {('+' + str(round((mean_h_p5 - mean_k_p5)*100, 1)) + '%'):<10}")
    print(f"{'Precision@10':<20} | {mean_k_p10:<18.4f} | {mean_h_p10:<18.4f} | {('+' + str(round((mean_h_p10 - mean_k_p10)*100, 1)) + '%'):<10}")
    print(f"{'Recall@10':<20} | {mean_k_rec:<18.4f} | {mean_h_rec:<18.4f} | {('+' + str(round((mean_h_rec - mean_k_rec)*100, 1)) + '%'):<10}")
    print(f"{'NDCG@10':<20} | {mean_k_ndcg:<18.4f} | {mean_h_ndcg:<18.4f} | {('+' + str(round((mean_h_ndcg - mean_k_ndcg)*100, 1)) + '%'):<10}")

    # =========================================================================
    # 2. DUPLICATE DETECTION & ENTITY RESOLUTION BENCHMARK
    # =========================================================================
    print("\n[BENCHMARK 2] DUPLICATE DETECTION & ENTITY RESOLUTION (MinHash LSH & DOI Matching)")
    print("-" * 80)

    planted_dups = ground_truth.get("planted_duplicates", [])
    test_papers = []
    expected_dup_pairs = set()

    for item in planted_dups:
        p1 = Paper.objects.filter(id=item["primary_id"]).first()
        p2 = Paper.objects.filter(id=item["duplicate_id"]).first()
        if p1 and p2:
            test_papers.append(UnifiedSearchService._paper_to_dict(p1))
            test_papers.append(UnifiedSearchService._paper_to_dict(p2))
            pair = tuple(sorted([p1.id, p2.id]))
            expected_dup_pairs.add(pair)

    # Also add 25 negative controls (non-duplicate papers)
    negative_controls = Paper.objects.exclude(id__in=[p["id"] for p in test_papers])[:25]
    for np in negative_controls:
        test_papers.append(UnifiedSearchService._paper_to_dict(np))

    # Run Entity Resolution
    deduped = EntityResolver.resolve_and_deduplicate(test_papers)

    # Check which planted duplicates were merged into the same cluster
    tp = 0
    fn = 0
    for p1_id, p2_id in expected_dup_pairs:
        merged = False
        for cluster in deduped:
            c_ids = set(cluster.get("cluster_ids", [cluster["id"]]))
            if p1_id in c_ids and p2_id in c_ids:
                merged = True
                break
        if merged:
            tp += 1
        else:
            fn += 1

    # False positives: negative control papers that were incorrectly merged with each other
    fp = 0
    neg_ids = {np.id for np in negative_controls}
    for cluster in deduped:
        c_ids = set(cluster.get("cluster_ids", [cluster["id"]]))
        merged_negs = c_ids & neg_ids
        if len(merged_negs) > 1:
            fp += (len(merged_negs) - 1)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    print(f"{'Input Paper Records Evaluated':<32}: {len(test_papers)}")
    print(f"{'Planted Duplicate Pairs':<32}: {len(expected_dup_pairs)}")
    print(f"{'True Duplicate Merges (TP)':<32}: {tp}")
    print(f"{'Missed Duplicate Pairs (FN)':<32}: {fn}")
    print(f"{'False Positive Merges (FP)':<32}: {fp}")
    print(f"{'Precision':<32}: {precision:.4f} ({precision*100:.1f}%)")
    print(f"{'Recall':<32}: {recall:.4f} ({recall*100:.1f}%)")
    print(f"{'F1 Score':<32}: {f1:.4f}")

    # =========================================================================
    # 3. RECOMMENDATION QUALITY BENCHMARK (HitRate@10 & MRR@10 vs Popularity)
    # =========================================================================
    print("\n[BENCHMARK 3] RECOMMENDATION QUALITY (HitRate@10 & MRR@10 vs. Popularity Baseline)")
    print("-" * 80)

    # Sample users with at least 5 saves for leave-one-out evaluation
    eligible_users = list(
        User.objects.annotate(save_c=Count("saved_research_items"))
        .filter(save_c__gte=4)
        .exclude(is_staff=True)[:20]
    )

    if not eligible_users:
        eligible_users = list(User.objects.filter(is_active=True).exclude(is_staff=True)[:10])

    pop_hits = 0
    pop_rr_sum = 0.0
    model_hits = 0
    model_rr_sum = 0.0
    eval_count = 0

    # Popularity baseline list
    popular_papers = list(Paper.objects.all().order_by("-save_count")[:10])
    pop_ids = [p.id for p in popular_papers]

    for user in eligible_users:
        user_saves = list(SavedResearchItem.objects.filter(user=user).select_related("resource"))
        if not user_saves:
            continue

        # Hold out the most recent save as ground truth target
        test_save = user_saves[-1]
        target_res = test_save.resource
        target_paper = Paper.objects.filter(
            Q(resource=target_res) | Q(canonical_doi=target_res.doi) | Q(arxiv_id=target_res.arxiv_id)
        ).first()

        if not target_paper:
            continue

        eval_count += 1
        target_id = target_paper.id

        # 1. Model Recommendations (Personalized content-based + CF)
        recs = RecommendationService.get_recommended_papers(
            user, limit=10, exclude_saved_item_ids=[test_save.id]
        )["papers"]
        rec_ids = [p.id for p in recs]

        if target_id in rec_ids:
            model_hits += 1
            rank = rec_ids.index(target_id) + 1
            model_rr_sum += 1.0 / rank

        # 2. Popularity Baseline Recommendations
        if target_id in pop_ids:
            pop_hits += 1
            rank = pop_ids.index(target_id) + 1
            pop_rr_sum += 1.0 / rank

    n_eval = max(1, eval_count)
    model_hr = model_hits / n_eval
    model_mrr = model_rr_sum / n_eval
    pop_hr = pop_hits / n_eval
    pop_mrr = pop_rr_sum / n_eval

    print(f"{'Evaluation Set (Leave-one-out)':<32}: {n_eval} members")
    print(f"{'Metric':<20} | {'Popularity Baseline':<20} | {'Personalized Recs':<20} | {'Gain':<10}")
    print("-" * 75)
    print(f"{'HitRate@10':<20} | {pop_hr:<20.4f} | {model_hr:<20.4f} | {('+' + str(round((model_hr - pop_hr)*100, 1)) + '%'):<10}")
    print(f"{'MRR@10':<20} | {pop_mrr:<20.4f} | {model_mrr:<20.4f} | {('+' + str(round((model_mrr - pop_mrr)*100, 1)) + '%'):<10}")

    # =========================================================================
    # 4. ANOMALY / SPAM & SPIKE DETECTION BENCHMARK
    # =========================================================================
    print("\n[BENCHMARK 4] ANOMALY & SPIKE DETECTION (Spam Accounts & Topic Spikes)")
    print("-" * 80)

    # 4a. Spam Account Detection
    ModerationFlag.objects.all().delete()
    detected_flags = AnomalyDetector.scan_for_anomalies()
    flagged_user_ids = {f.user_id for f in detected_flags}
    planted_spam = ground_truth.get("planted_spam_accounts", [])
    expected_spam_ids = {s["user_id"] for s in planted_spam}

    spam_tp = len(flagged_user_ids & expected_spam_ids)
    spam_fp = len(flagged_user_ids - expected_spam_ids)
    spam_fn = len(expected_spam_ids - flagged_user_ids)

    spam_p = spam_tp / (spam_tp + spam_fp) if (spam_tp + spam_fp) > 0 else 1.0
    spam_r = spam_tp / (spam_tp + spam_fn) if (spam_tp + spam_fn) > 0 else 0.0
    spam_f1 = (2 * spam_p * spam_r) / (spam_p + spam_r) if (spam_p + spam_r) > 0 else 0.0

    print(f"--- Spam & Anomaly Account Detection ---")
    print(f"{'Planted Spam Accounts':<32}: {len(expected_spam_ids)}")
    print(f"{'Detected Spam Accounts (TP)':<32}: {spam_tp}")
    print(f"{'False Positives (FP)':<32}: {spam_fp}")
    print(f"{'Precision':<32}: {spam_p:.4f} ({spam_p*100:.1f}%)")
    print(f"{'Recall':<32}: {spam_r:.4f} ({spam_r*100:.1f}%)")
    print(f"{'F1 Score':<32}: {spam_f1:.4f}")

    # 4b. Topic Spike Detection
    calculated_trends = TrendAnalyzer.calculate_topic_trends(window_days=7, baseline_days=30)
    detected_spikes = {t.topic_id for t in calculated_trends if t.is_spike}
    planted_spikes = ground_truth.get("planted_topic_spikes", [])
    expected_spike_ids = {s["topic_id"] for s in planted_spikes}

    spike_tp = len(detected_spikes & expected_spike_ids)
    spike_fp = len(detected_spikes - expected_spike_ids)
    spike_fn = len(expected_spike_ids - detected_spikes)

    spike_p = spike_tp / (spike_tp + spike_fp) if (spike_tp + spike_fp) > 0 else 1.0
    spike_r = spike_tp / (spike_tp + spike_fn) if (spike_tp + spike_fn) > 0 else 0.0
    spike_f1 = (2 * spike_p * spike_r) / (spike_p + spike_r) if (spike_p + spike_r) > 0 else 0.0

    print(f"\n--- Statistical Topic Spike Detection (Z-score >= 2.0) ---")
    print(f"{'Planted Topic Spikes':<32}: {len(expected_spike_ids)}")
    print(f"{'Detected Spikes (TP)':<32}: {spike_tp}")
    print(f"{'False Positive Spikes (FP)':<32}: {spike_fp}")
    print(f"{'Precision':<32}: {spike_p:.4f}")
    print(f"{'Recall':<32}: {spike_r:.4f}")
    print(f"{'F1 Score':<32}: {spike_f1:.4f}")

    # =========================================================================
    # 5. RAG ASSISTANT CITATION FAITHFULNESS & RETRIEVAL RECALL@K
    # =========================================================================
    print("\n[BENCHMARK 5] RAG RESEARCH ASSISTANT (Retrieval Recall@5 & Citation Faithfulness)")
    print("-" * 80)

    rag_questions = ground_truth.get("rag_benchmark_questions", [])
    if not rag_questions:
        rag_questions = [
            {
                "question": "How does AlphaFold predict 3D protein structures?",
                "expected_keywords": ["protein", "structure", "atomic"],
                "expected_paper_id": 11,
            }
        ]

    rag_recall_hits = 0
    citation_present_count = 0
    keyword_grounding_scores = []

    for item in rag_questions:
        q = item["question"]
        expected_pid = item.get("expected_paper_id")
        expected_kws = item.get("expected_keywords", [])

        res = ResearchAssistantService.ask(q, top_k=5)
        retrieved_pids = [s["paper_id"] for s in res.get("sources", [])]

        # 1. Retrieval Recall@5
        if expected_pid and expected_pid in retrieved_pids:
            rag_recall_hits += 1

        # 2. Citation check: does the answer contain [1], [2], etc.?
        answer_text = res.get("answer", "")
        has_citations = bool(re.search(r"\[\d+\]", answer_text))
        if has_citations:
            citation_present_count += 1

        # 3. Grounding faithfulness: are expected key factual terms present?
        found_kw = sum(1 for kw in expected_kws if kw.lower() in answer_text.lower())
        kw_score = found_kw / max(1, len(expected_kws))
        keyword_grounding_scores.append(kw_score)

    total_rag = max(1, len(rag_questions))
    retrieval_recall = rag_recall_hits / total_rag
    citation_rate = citation_present_count / total_rag
    avg_faithfulness = sum(keyword_grounding_scores) / total_rag

    print(f"{'Questions Evaluated':<32}: {total_rag}")
    print(f"{'Retrieval Recall@5':<32}: {retrieval_recall:.4f} ({retrieval_recall*100:.1f}%)")
    print(f"{'Citation Inclusion Rate [1], [2]':<32}: {citation_rate:.4f} ({citation_rate*100:.1f}%)")
    print(f"{'Factual Faithfulness Score':<32}: {avg_faithfulness:.4f} ({avg_faithfulness*100:.1f}%)")

    print("\n" + "=" * 80)
    print("ALL QUANTITATIVE EVALUATIONS FINISHED WITH NUMERIC BENCHMARK OUTPUTS")
    print("=" * 80)


if __name__ == "__main__":
    run_evaluation_suite()
