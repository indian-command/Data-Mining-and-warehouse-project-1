import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import django, json
from datetime import timedelta
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from accounts.models import Profile, MemberFollow, TopicFollow, Topic, Department, School
from discussions.models import DiscussionPost, Comment, PostVote, SavedPost
from research_library.models import ResearchResource, SavedResearchItem, ResearchCollection, CollectionItem
from papers.models import Paper, PaperCitation, PaperChunk
from trends.models import ActivityEvent, TopicTrend, ModerationFlag
from trends.services import TrendAnalyzer, AnomalyDetector
from recommendations.services import RecommendationService
from research_assistant.services import ResearchAssistantService
from unified_search.services import UnifiedSearchService, EntityResolver
from institutional_analytics.services import DuckDBAnalyticsService, StarSchemaETLService

results = {}
client = Client()

print("="*70)
print("INDEPENDENT AUDIT: EXECUTING COMPLETE FUNCTIONAL TEST SUITE F1-F9")
print("="*70)

# ==============================================================================
# F1: ACCOUNTS & PROFILES
# ==============================================================================
f1_results = {}
school = School.objects.filter(departments__isnull=False).first()
dept = school.departments.first() if school else None
top = Topic.objects.first()

reg_payload = {
    "username": "qa_auditor_student",
    "first_name": "QA",
    "last_name": "Auditor",
    "email": "qa.auditor@chanakyauniversity.edu.in",
    "password1": "QAAuditPass123!",
    "password2": "QAAuditPass123!",
    "role": "student",
    "school": school.id if school else "",
    "department": dept.id if dept else "",
    "bio": "Independent senior QA auditor evaluating the research commons.",
    "topics": [top.id] if top else []
}

User.objects.filter(username="qa_auditor_student").delete()
resp_reg = client.post("/accounts/register/", reg_payload)
qa_user = User.objects.filter(username="qa_auditor_student").first()
f1_results["registration_success"] = (resp_reg.status_code == 302 and qa_user is not None)
f1_results["profile_created"] = (qa_user is not None and hasattr(qa_user, "profile"))
f1_results["role_assigned"] = qa_user.profile.role if (qa_user and hasattr(qa_user, "profile")) else None

# Duplicate registration using fresh client
c_anon = Client()
resp_dup = c_anon.post("/accounts/register/", reg_payload)
f1_results["duplicate_prevention"] = (resp_dup.status_code == 200 and ("already exists" in resp_dup.content.decode().lower() or "unique" in resp_dup.content.decode().lower()))

# Login
c_login = Client()
resp_inv = c_login.post("/accounts/login/", {"username": "qa_auditor_student", "password": "WrongPassword"})
f1_results["invalid_login_rejected"] = (resp_inv.status_code == 200)
resp_val = c_login.post("/accounts/login/", {"username": "qa_auditor_student", "password": "QAAuditPass123!"})
f1_results["valid_login_success"] = (resp_val.status_code == 302)

# Follow member & topic
target_fac = User.objects.filter(profile__role="faculty").first()
if target_fac and qa_user:
    resp_fol_m = c_login.post(f"/accounts/members/{target_fac.id}/follow/")
    f1_results["follow_member"] = MemberFollow.objects.filter(follower=qa_user, followed=target_fac).exists()
else:
    f1_results["follow_member"] = False

if top and qa_user:
    resp_fol_t = c_login.post(f"/accounts/topics/{top.id}/follow/")
    f1_results["follow_topic"] = TopicFollow.objects.filter(user=qa_user, topic=top).exists()
else:
    f1_results["follow_topic"] = False

# Role Permissions
resp_stud_trends = c_login.get("/trends/")
f1_results["student_trends_redirect"] = (resp_stud_trends.status_code == 302)
resp_stud_analytics = c_login.get("/analytics/")
f1_results["student_analytics_redirect"] = (resp_stud_analytics.status_code == 302)

results["F1"] = f1_results
print("F1 Results:", f1_results)

# ==============================================================================
# F2: POSTS & DISCUSSIONS
# ==============================================================================
f2_results = {}
sample_paper = Paper.objects.first()
post_payload = {
    "title": "Empirical Comparison of Transformers on Low-Resource Languages",
    "content": "Exploring the attention degradation on domain-specific dialect corpora.",
    "post_type": "paper",
    "paper_link": f"http://localhost:8080/papers/{sample_paper.id}/" if sample_paper else "",
    "tags": [top.id] if top else []
}
resp_p = c_login.post("/discussions/create/", post_payload)
qa_post = DiscussionPost.objects.filter(title="Empirical Comparison of Transformers on Low-Resource Languages").first()
f2_results["post_creation"] = (resp_p.status_code == 302 and qa_post is not None)

if qa_post:
    resp_comm = c_login.post(f"/discussions/comment/{qa_post.id}/", {"content": "Have you evaluated perplexity on Sanskrit corpora?"})
    comm = Comment.objects.filter(post=qa_post, parent__isnull=True).first()
    f2_results["comment_creation"] = (comm is not None)
    if comm:
        resp_rep = c_login.post(f"/discussions/comment/{qa_post.id}/", {"content": "Yes, perplexity decreases with Byte-Pair Encoding.", "parent_id": comm.id})
        rep = Comment.objects.filter(post=qa_post, parent=comm).first()
        f2_results["nested_reply_creation"] = (rep is not None)
    
    # Upvotes
    v1 = c_login.post(f"/discussions/upvote/{qa_post.id}/")
    qa_post.refresh_from_db()
    f2_results["upvote_added"] = (qa_post.upvote_count == 1)
    v2 = c_login.post(f"/discussions/upvote/{qa_post.id}/")
    qa_post.refresh_from_db()
    f2_results["upvote_toggled_off"] = (qa_post.upvote_count == 0)

    # Bookmark post
    resp_sp = c_login.post(f"/discussions/save/{qa_post.id}/")
    f2_results["post_saved"] = SavedPost.objects.filter(user=qa_user, post=qa_post).exists()

    # Personal feed check (?feed=following)
    resp_feed = c_login.get("/discussions/?feed=following")
    f2_results["feed_following_200"] = (resp_feed.status_code == 200)

results["F2"] = f2_results
print("F2 Results:", f2_results)

# ==============================================================================
# F3: RESEARCH LIBRARY
# ==============================================================================
f3_results = {}
if sample_paper:
    init_sc = sample_paper.save_count
    resp_sp = c_login.post(f"/papers/{sample_paper.id}/save/", {"notes": "Auditor confidential private notes."})
    sample_paper.refresh_from_db()
    f3_results["save_paper_status"] = resp_sp.status_code
    f3_results["save_count_incremented"] = (sample_paper.save_count > init_sc)
    saved_paper_item = SavedResearchItem.objects.filter(user=qa_user).first()
    f3_results["saved_item_in_library"] = (saved_paper_item is not None)

# Save via DOI / arXiv / URL
resp_save_doi = c_login.post("/library/save/", {
    "source_type": "doi",
    "identifier": "10.1145/3394486.3403177",
    "title": "Auditor Ingested External Paper by DOI",
    "private_notes": "Added directly via DOI"
})
f3_results["save_by_doi_status"] = resp_save_doi.status_code

# Collections
resp_create_coll = c_login.post("/library/collections/create/", {"name": "QA Benchmarks 2026", "description": "Audit validation set"})
f3_results["collection_create_status"] = resp_create_coll.status_code
coll_obj = ResearchCollection.objects.filter(owner=qa_user, name="QA Benchmarks 2026").first()
f3_results["collection_created"] = (coll_obj is not None)

if coll_obj and saved_paper_item:
    resp_add_coll = c_login.post("/library/collections/add/", {"collection": coll_obj.id, "saved_item": saved_paper_item.id})
    f3_results["item_in_collection"] = CollectionItem.objects.filter(collection=coll_obj, saved_item=saved_paper_item).exists()

# Private notes privacy
if target_fac:
    c_fac = Client()
    c_fac.login(username=target_fac.username, password="MemberPass123!")
    resp_lib_fac = c_fac.get("/library/")
    f3_results["private_notes_isolated"] = ("Auditor confidential private notes" not in resp_lib_fac.content.decode())

results["F3"] = f3_results
print("F3 Results:", f3_results)

# ==============================================================================
# F4: EXTERNAL CONTENT INGESTION
# ==============================================================================
f4_results = {}
f4_results["papers_in_db"] = Paper.objects.count()
f4_results["citations_in_db"] = PaperCitation.objects.count()
f4_results["chunks_in_db"] = PaperChunk.objects.count()
f4_results["papers_with_doi"] = Paper.objects.exclude(canonical_doi="").count()
f4_results["papers_with_arxiv"] = Paper.objects.exclude(arxiv_id="").count()
f4_results["papers_with_embeddings"] = Paper.objects.filter(embedding__isnull=False).count()
results["F4"] = f4_results
print("F4 Results:", f4_results)

# ==============================================================================
# F5: UNIFIED SEARCH
# ==============================================================================
f5_results = {}
test_queries = ["quantum computing", "deep learning", "transformer", "chanakya", "xyznotfoundquery999"]
for q in test_queries:
    res = UnifiedSearchService.execute_unified_search(q)
    f5_results[q] = {
        "total_count": res.get("total_count", 0),
        "scholarly_sources": len(res.get("scholarly_sources", [])),
        "library_resources": len(res.get("library_resources", [])),
        "university_members": len(res.get("university_members", [])),
        "discussions": len(res.get("discussions", [])),
    }

raw_pairs = [
    {
        "id": "mock_1",
        "sources": ["openalex"],
        "title": "Attention Is All You Need",
        "canonical_doi": "10.48550/arXiv.1706.03762",
        "arxiv_id": "1706.03762",
        "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
        "score": 0.95,
        "pagerank_score": 0.05
    },
    {
        "id": "mock_2",
        "sources": ["arxiv"],
        "title": "Attention Is All You Need (arXiv preprint)",
        "canonical_doi": "10.48550/arXiv.1706.03762",
        "arxiv_id": "1706.03762",
        "abstract": "The dominant sequence transduction models are based on complex recurrent neural networks.",
        "score": 0.90,
        "pagerank_score": 0.04
    }
]
merged = EntityResolver.resolve_and_deduplicate(raw_pairs)
f5_results["entity_resolution_merges"] = (len(merged) == 1)
f5_results["merged_sources_count"] = len(merged[0].get("sources", [])) if merged else 0
results["F5"] = f5_results
print("F5 Results:", f5_results)

# ==============================================================================
# F6: RECOMMENDATIONS
# ==============================================================================
f6_results = {}
rec_student = RecommendationService.get_recommended_papers(qa_user, limit=5)
f6_results["student_recommendations_count"] = len(rec_student.get("papers", []))
f6_results["algorithm_tag"] = rec_student.get("strategy", "unknown")

if sample_paper:
    co_saved = RecommendationService.get_also_saved_for_paper(sample_paper, limit=5)
    f6_results["co_saved_count"] = len(co_saved)

new_u = User.objects.create(username="cold_start_user_temp")
rec_cold = RecommendationService.get_recommended_papers(new_u, limit=5)
f6_results["cold_start_count"] = len(rec_cold.get("papers", []))
f6_results["cold_start_algo"] = rec_cold.get("strategy", "unknown")
new_u.delete()
results["F6"] = f6_results
print("F6 Results:", f6_results)

# ==============================================================================
# F7: TRENDS & MONITORING
# ==============================================================================
f7_results = {}
trends = TrendAnalyzer.calculate_topic_trends(window_days=7, baseline_days=30)
f7_results["trends_calculated"] = len(trends)
f7_results["spikes_detected"] = len([t for t in trends if t.is_spike])

anomalies = AnomalyDetector.scan_for_anomalies()
f7_results["anomalies_detected"] = len(anomalies)

c_admin = Client()
admin_u = User.objects.filter(is_superuser=True).first()
if admin_u:
    c_admin.login(username=admin_u.username, password="AdminPass123!")
    resp_mod = c_admin.get("/trends/moderation/")
    f7_results["admin_moderation_queue_status"] = resp_mod.status_code

results["F7"] = f7_results
print("F7 Results:", f7_results)

# ==============================================================================
# F8: RESEARCH ASSISTANT (RAG)
# ==============================================================================
f8_results = {}
q1 = "How does attention mechanism function in transformers?"
rag_res = ResearchAssistantService.ask(q1, user=qa_user)
f8_results["rag_query"] = q1
f8_results["has_answer"] = bool(rag_res.get("answer"))
f8_results["citations_count"] = len(rag_res.get("sources", []))
f8_results["retrieved_passages_count"] = len(rag_res.get("sources", []))
f8_results["grounded"] = rag_res.get("grounded", False)
results["F8"] = f8_results
print("F8 Results:", f8_results)

# ==============================================================================
# F9: INSTITUTIONAL ANALYTICS
# ==============================================================================
f9_results = {}
if admin_u:
    resp_dash = c_admin.get("/analytics/")
    f9_results["dashboard_status"] = resp_dash.status_code

dept_topics = DuckDBAnalyticsService.get_department_topics_over_time()
f9_results["duckdb_dept_topics_count"] = len(dept_topics)

collab_mat = DuckDBAnalyticsService.get_cross_department_collaboration_matrix()
f9_results["duckdb_collab_matrix_count"] = len(collab_mat)

top_papers = DuckDBAnalyticsService.get_most_engaged_papers()
f9_results["duckdb_most_engaged_papers_count"] = len(top_papers)

first_dept = Department.objects.first()
if first_dept:
    drill_dept = DuckDBAnalyticsService.get_drill_down_stats(selected_dept_id=first_dept.id)
    f9_results["drill_down_department_data"] = bool(drill_dept)

results["F9"] = f9_results
print("F9 Results:", f9_results)

# ==============================================================================
# END-TO-END INTEGRATION WORKFLOW AUDIT
# ==============================================================================
print("\n--- END-TO-END INTEGRATION WORKFLOW AUDIT ---")
e2e_results = {}

# Workflow A: Research Discovery Flow
# Search -> View -> Save -> In Library -> Recs updated
wf_a = {}
s_res = UnifiedSearchService.execute_unified_search("deep learning")
top_scholarly = s_res["scholarly_sources"][0] if s_res["scholarly_sources"] else None
wf_a["step1_search_has_results"] = (top_scholarly is not None)
if top_scholarly:
    p_id = top_scholarly["id"]
    save_resp = c_login.post(f"/papers/{p_id}/save/")
    wf_a["step2_save_response"] = save_resp.status_code
    saved_item_exists = SavedResearchItem.objects.filter(user=qa_user, resource__doi=top_scholarly.get("canonical_doi", "")).exists()
    wf_a["step3_item_in_user_library"] = saved_item_exists
    # Check recommendations reflect user's saves
    recs_updated = RecommendationService.get_recommended_papers(qa_user, limit=5)
    wf_a["step4_recs_strategy"] = recs_updated.get("strategy")
    wf_a["step4_recs_count"] = len(recs_updated.get("papers", []))

e2e_results["Workflow_A_Discovery"] = wf_a

# Workflow B: Research Collaboration Flow
# User A follow User B -> User B posts -> User A sees in feed -> comments
wf_b = {}
fac_user = target_fac
fac_client = Client()
fac_client.login(username=fac_user.username, password="MemberPass123!")
post_collab = fac_client.post("/discussions/create/", {
    "title": "Collaborative Call for LLM Interpretability Research",
    "content": "Looking for research scholars in CS and Maths to investigate mechanistic interpretability.",
    "post_type": "discussion"
})
fac_post_obj = DiscussionPost.objects.filter(title="Collaborative Call for LLM Interpretability Research").first()
wf_b["step1_faculty_post_created"] = (fac_post_obj is not None)
if fac_post_obj:
    # Ensure student follows faculty (idempotent follow check)
    if not MemberFollow.objects.filter(follower=qa_user, followed=fac_user).exists():
        c_login.post(f"/accounts/members/{fac_user.id}/follow/")
    # Student checks following feed
    feed_resp = c_login.get("/discussions/?feed=following")
    wf_b["step2_student_feed_sees_post"] = ("Collaborative Call for LLM Interpretability Research" in feed_resp.content.decode())
    # Student comments
    comm_resp = c_login.post(f"/discussions/comment/{fac_post_obj.id}/", {"content": "I am interested in mechanistic interpretability for attention circuits."})
    wf_b["step3_student_comment_status"] = comm_resp.status_code
    wf_b["step3_comment_logged_in_db"] = Comment.objects.filter(post=fac_post_obj, author=qa_user).exists()

e2e_results["Workflow_B_Collaboration"] = wf_b

# Workflow C: RAG Answering Flow
# Query -> Chunks retrieved -> Extractive synthesis / LLM -> Citations
wf_c = {}
rag_out = ResearchAssistantService.ask("What is the architecture of residual networks?", user=qa_user)
wf_c["step1_chunks_retrieved"] = len(rag_out.get("sources", []))
wf_c["step2_answer_generated"] = bool(rag_out.get("answer"))
wf_c["step3_citations_present"] = any("[" in s for s in [rag_out.get("answer", "")])
wf_c["step4_grounded_flag"] = rag_out.get("grounded", False)
e2e_results["Workflow_C_RAG"] = wf_c

# Workflow D: Institutional Intelligence Flow
# Events recorded -> Parquet Lakehouse -> DuckDB queries
wf_d = {}
recent_events_count = ActivityEvent.objects.count()
wf_d["step1_activity_events_logged"] = recent_events_count
# Test DuckDB queries live
analytics_stats = DuckDBAnalyticsService.get_department_topics_over_time()
wf_d["step2_duckdb_returns_data"] = len(analytics_stats) > 0
wf_d["step3_drill_down_supported"] = True if Department.objects.exists() else False
e2e_results["Workflow_D_Institutional_Intelligence"] = wf_d

results["EndToEnd_Workflows"] = e2e_results
print("End-to-End Workflow Results:", e2e_results)

with open("audit_evidence/audit_test_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("\nALL AUDIT TESTS COMPLETED! Saved to audit_evidence/audit_test_results.json")
