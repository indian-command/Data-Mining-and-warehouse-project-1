import os
import sys
import random
import json
import math
from pathlib import Path
from datetime import datetime, timedelta

# Ensure Django environment is configured
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
import networkx as nx

from accounts.models import School, Department, Topic, Profile, MemberFollow, TopicFollow
from discussions.models import DiscussionPost, Comment, PostVote
from research_library.models import ResearchResource, SavedResearchItem, ResearchCollection, CollectionItem
from papers.models import Paper, PaperCitation, PaperChunk
from papers.services import EmbeddingService, TextChunker, IngestionPipeline
from trends.models import ActivityEvent, TopicTrend, ModerationFlag
from trends.services import TrendAnalyzer, AnomalyDetector
from institutional_analytics.services import StarSchemaETLService

User = get_user_model()


def run_synthetic_generator():
    print("=" * 70)
    print("CHANAKYA RESEARCH COMMONS: SYNTHETIC DATA GENERATOR & SEEDER")
    print("=" * 70)

    random.seed(42)

    # -------------------------------------------------------------
    # 1. SCHOOLS & DEPARTMENTS (6+ Departments across 3 Schools)
    # -------------------------------------------------------------
    print("\n[1/7] Creating Schools, Departments, and Research Topics...")

    schools_data = [
        ("School of Technology & Computing", "STC", "Advancing AI, computing systems, and data science."),
        ("School of Biological Sciences", "SBS", "Research in molecular biology, genomics, and biopharma."),
        ("School of Sustainable Development & Policy", "SSDP", "Interdisciplinary studies in sustainability, policy, and math."),
    ]
    school_objs = {}
    for name, code, desc in schools_data:
        s, _ = School.objects.get_or_create(code=code, defaults={"name": name, "description": desc})
        school_objs[code] = s

    depts_data = [
        ("Computer Science & AI", "CSAI", "STC", "Machine learning, NLP, computer vision, and systems."),
        ("Data Science & Analytics", "DSA", "STC", "Statistical learning, big data, and data engineering."),
        ("Biotechnology & Bioinformatics", "BTBI", "SBS", "Genomic sequences, computational biology, and healthcare."),
        ("Mathematics & Computing", "MCS", "SSDP", "Discrete algorithms, optimization, and quantum mathematics."),
        ("Environmental Science & Sustainable Tech", "ESST", "SSDP", "Climate modeling, renewable energy, and eco-systems."),
        ("Public Policy & Governance", "PPG", "SSDP", "Technology policy, institutional analytics, and ethics."),
    ]
    dept_objs = {}
    for name, code, scode, desc in depts_data:
        d, _ = Department.objects.get_or_create(
            code=code,
            defaults={"name": name, "school": school_objs[scode], "description": desc}
        )
        dept_objs[code] = d

    topics_data = [
        ("Deep Learning", "Neural networks, optimization, and backprop"),
        ("Natural Language Processing", "Transformers, LLMs, and language generation"),
        ("Computer Vision", "Convolutional architectures and visual segmentation"),
        ("Genomics & Bioinformatics", "Sequence alignment, protein folding, and genomic variants"),
        ("Reinforcement Learning", "Policy gradient, MDPs, and agentic systems"),
        ("Climate Modeling", "Atmospheric simulations and carbon sequestration"),
        ("Quantum Computing", "Qubits, quantum algorithms, and error correction"),
        ("Autonomous Robotics", "Kinematics, path planning, and sim-to-real"),
        ("Statistical Physics", "Complex systems, phase transitions, and network science"),
        ("Technology Policy", "Ethical AI, data governance, and regulatory frameworks"),
        ("Renewable Energy Systems", "Photovoltaics, battery tech, and smart grids"),
        ("Graph Neural Networks", "Node classification, link prediction, and molecular graphs"),
    ]
    topic_objs = {}
    for t_name, t_desc in topics_data:
        t, _ = Topic.objects.get_or_create(name=t_name, defaults={"description": t_desc})
        topic_objs[t_name] = t

    # -------------------------------------------------------------
    # 2. UNIVERSITY MEMBERS (55+ Members across 6 Departments)
    # -------------------------------------------------------------
    print("\n[2/7] Creating 55+ University Members (Faculty, Researchers, Students, Admins)...")

    first_names = [
        "Aarav", "Aditi", "Rohan", "Priya", "Ananya", "Vikram", "Neha", "Rahul", "Pooja", "Arjun",
        "Divya", "Siddharth", "Meera", "Kavya", "Varun", "Ishaan", "Sneha", "Aditya", "Rhea", "Gaurav",
        "Tanvi", "Naveen", "Tara", "Akash", "Shreya", "Karan", "Simran", "Deepak", "Swati", "Manish",
        "Elena", "David", "Sophia", "Michael", "Amara", "Lucas", "Maya", "Alexander", "Fatima", "Wei"
    ]
    last_names = [
        "Sharma", "Patel", "Verma", "Rao", "Iyer", "Nair", "Kulkarni", "Deshmukh", "Chopra", "Reddy",
        "Menon", "Bose", "Banerjee", "Chatterjee", "Gupta", "Malhotra", "Kapoor", "Bhat", "Joshi", "Mishra",
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"
    ]

    dept_list = list(dept_objs.values())
    topic_list = list(topic_objs.values())

    member_users = []
    # Ensure one primary admin account
    admin_user, _ = User.objects.get_or_create(
        username="chanakya_admin",
        defaults={
            "email": "admin@chanakya.edu.in",
            "first_name": "Admin",
            "last_name": "Chanakya",
            "is_staff": True,
            "is_superuser": True,
        }
    )
    admin_user.set_password("AdminPass123!")
    admin_user.save()
    p, _ = Profile.objects.get_or_create(
        user=admin_user,
        defaults={"role": "admin", "department": dept_list[0], "bio": "Chief Research Administrator"}
    )
    p.topics.add(*topic_list[:4])
    member_users.append(admin_user)

    for i in range(1, 55):
        uname = f"member_{i}"
        fn = first_names[(i * 3) % len(first_names)]
        ln = last_names[(i * 7) % len(last_names)]
        email = f"{uname}@chanakya.edu.in"
        role = "faculty" if i <= 10 else ("researcher" if i <= 22 else "student")
        dept = dept_list[i % len(dept_list)]

        user, created = User.objects.get_or_create(
            username=uname,
            defaults={"email": email, "first_name": fn, "last_name": ln}
        )
        if created:
            user.set_password("MemberPass123!")
            user.save()

        profile, _ = Profile.objects.get_or_create(
            user=user,
            defaults={
                "role": role,
                "department": dept,
                "bio": f"{role.title()} in {dept.name} investigating modern academic frontiers.",
                "research_interests": f"Applied research in {topic_list[i % len(topic_list)].name} and computational paradigms."
            }
        )
        assigned_topics = [topic_list[i % len(topic_list)], topic_list[(i + 2) % len(topic_list)]]
        profile.topics.set(assigned_topics)
        member_users.append(user)

    # Follow graphs
    for u in member_users[:30]:
        candidates = [o for o in member_users if o.id != u.id]
        targets = random.sample(candidates, k=random.randint(3, 8))
        for t in targets:
            MemberFollow.objects.get_or_create(follower=u, followed=t)
        for top in random.sample(topic_list, k=random.randint(2, 4)):
            TopicFollow.objects.get_or_create(user=u, topic=top)

    # -------------------------------------------------------------
    # 3. 500+ SCHOLARLY PAPERS ACROSS DEPARTMENTS & CITATION GRAPH
    # -------------------------------------------------------------
    print("\n[3/7] Generating 520+ Scholarly Papers with Embeddings & Chunks...")

    paper_seeds = [
        # AI & CS
        ("Attention Is All You Need in Transformers", "Introduces the Transformer model based solely on self-attention mechanisms, dispensing with recurrence and convolutions entirely.", "10.1145/10001", "1706.03762", ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"], "NeurIPS", 2017, ["Deep Learning", "Natural Language Processing"]),
        ("Deep Residual Learning for Image Recognition", "Presents a residual learning framework to ease the training of networks that are substantially deeper than those used previously.", "10.1145/10002", "1512.03385", ["Kaiming He", "Xiangyu Zhang", "Shaoqing Ren"], "CVPR", 2016, ["Computer Vision", "Deep Learning"]),
        ("BERT: Pre-training of Deep Bidirectional Transformers", "Introduces a new language representation model designed to pretrain deep bidirectional representations from unlabeled text.", "10.1145/10003", "1810.04805", ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee"], "NAACL", 2019, ["Natural Language Processing"]),
        ("Language Models are Few-Shot Learners", "Demonstrates that scaling language models greatly improves task-agnostic, few-shot performance on diverse NLP benchmarks.", "10.1145/10004", "2005.14165", ["Tom Brown", "Benjamin Mann", "Nick Ryder"], "NeurIPS", 2020, ["Natural Language Processing"]),
        ("Mastering the Game of Go with Deep Neural Networks", "Combines tree search with deep neural networks trained via supervised learning from human expert games and reinforcement learning from self-play.", "10.1038/nature16961", "1603.04467", ["David Silver", "Aja Huang", "Chris Maddison"], "Nature", 2016, ["Reinforcement Learning"]),
        ("Adam: A Method for Stochastic Optimization", "A method for efficient stochastic optimization that only requires first-order gradients with little memory requirement.", "10.1145/10006", "1412.6980", ["Diederik Kingma", "Jimmy Ba"], "ICLR", 2015, ["Deep Learning"]),
        ("Generative Adversarial Nets", "Proposes a framework for estimating generative models via an adversarial process with two models: a generative model and a discriminative model.", "10.1145/10007", "1406.2661", ["Ian Goodfellow", "Jean Pouget-Abadie", "Mehdi Mirza"], "NeurIPS", 2014, ["Deep Learning", "Computer Vision"]),
        ("Graph Convolutional Networks for Semi-Supervised Classification", "Presents a scalable approach for semi-supervised learning on graph-structured data based on an efficient layer-wise propagation rule.", "10.1145/10008", "1609.02907", ["Thomas Kipf", "Max Welling"], "ICLR", 2017, ["Graph Neural Networks"]),
        ("Constitutional AI: A Framework for Self-Improving Alignment", "Describes training AI models using a set of explicit behavioral principles without requiring human feedback labels.", "10.1145/10009", "2212.08073", ["Yuntao Bai", "Saurav Kadavath", "Andy Kundu"], "arXiv", 2022, ["Natural Language Processing", "Technology Policy"]),
        ("Llama: Open and Efficient Foundation Language Models", "A collection of foundation language models ranging from 7B to 65B parameters trained on trillions of publicly available tokens.", "10.1145/10010", "2302.13971", ["Hugo Touvron", "Thibaut Lavril", "Gautier Izacard"], "arXiv", 2023, ["Natural Language Processing"]),

        # Genomics & Biotech
        ("Highly Accurate Protein Structure Prediction with AlphaFold", "Demonstrates computational prediction of 3D protein structures from primary amino acid sequence with atomic accuracy.", "10.1038/s41586-021-03819-2", "2107.03378", ["John Jumper", "Richard Evans", "Alexander Pritzel"], "Nature", 2021, ["Genomics & Bioinformatics"]),
        ("Genome-wide CRISPR-Cas9 Screening in Human Cells", "Presents scalable methodologies for knocking out genes systematically across human cell lines to assess functional genomics.", "10.1126/science.1246981", "1401.0001", ["Feng Zhang", "Le Cong", "Patrick Hsu"], "Science", 2014, ["Genomics & Bioinformatics"]),
        ("Single-Cell RNA Sequencing Analysis Pipelines", "High-throughput microfluidic droplets enable unbiased characterization of tens of thousands of single-cell transcriptomes.", "10.1016/j.cell.2015.05.002", "1505.0001", ["Evan Macosko", "Aviv Regev", "Alex Shalek"], "Cell", 2015, ["Genomics & Bioinformatics"]),
        ("Variant Effect Prediction via Deep Sequence Models", "Transformer-based nucleotide models predict the functional regulatory impact of non-coding human genetic variations.", "10.1038/s41588-023-01452", "2305.12001", ["Maya Chen", "Julian Ross", "Sarah Alami"], "Nature Genetics", 2023, ["Genomics & Bioinformatics"]),
        ("De Novo Design of Protein Binders with Generative Diffusion", "Employs score-based generative diffusion models to construct de novo macrocyclic and globular binding proteins against cancer targets.", "10.1038/s41586-023-06415-8", "2308.01234", ["David Baker", "Brian Coventry", "Nate Bennett"], "Nature", 2023, ["Genomics & Bioinformatics"]),

        # Mathematics, Quantum & Environment
        ("Quantum Supremacy Using a Programmable Superconducting Processor", "Demonstrates computational capability on a quantum processor beyond the reach of any classical supercomputer.", "10.1038/s41586-019-1666-5", "1910.11333", ["Frank Arute", "Kunai Arya", "John Martinis"], "Nature", 2019, ["Quantum Computing"]),
        ("Surface Codes for Fault-Tolerant Quantum Computation", "An introduction to 2D topological surface code architectures that achieve high error thresholds under local measurement constraints.", "10.1103/PhysRevA.86.032324", "1208.0928", ["Austin Fowler", "Marten Mariantoni", "John Martinis"], "Phys. Rev. A", 2012, ["Quantum Computing"]),
        ("Global Carbon Budgets and Climate Sensitivity Pathways", "Synthesizes empirical and modeled feedback loops between terrestrial carbon sinks and greenhouse forcing trajectories.", "10.1038/s41558-020-0731-2", "2003.09001", ["Pierre Friedlingstein", "Corinne Le Quéré", "Robbie Andrew"], "Nature Climate Change", 2020, ["Climate Modeling", "Renewable Energy Systems"]),
        ("Next-Generation Solid-State Electrolytes for High-Capacity Batteries", "Investigates sulfide and garnet ceramic solid electrolytes that mitigate lithium dendrite penetration in EV batteries.", "10.1038/s41560-021-00832-0", "2106.04412", ["Linda Nazar", "Ying Shirley Meng", "Kiyoshi Kanamura"], "Nature Energy", 2021, ["Renewable Energy Systems"]),
        ("Ethical Governance of Frontier AI Systems in Higher Education", "Evaluates institutional risk governance, academic integrity frameworks, and intellectual property attribution for generative LLMs.", "10.1145/3593013.3594000", "2304.09911", ["Kiran Rao", "Meera Kulkarni", "Vikram Nair"], "ACM FAccT", 2023, ["Technology Policy"]),
    ]

    # Generate total 525 papers by procedurally extending the high-impact base
    all_paper_records = []
    base_titles = [s[0] for s in paper_seeds]
    base_abstracts = [s[1] for s in paper_seeds]

    qualifiers = [
        "A Comprehensive Survey of", "Empirical Benchmarking of", "Theoretical Foundations of",
        "Algorithmic Advances in", "Robust Optimization for", "Scalable Architectures for",
        "Decentralized Frameworks for", "Statistical Inference in", "Multi-Agent Coordination in",
        "Safety and Verification in", "Cross-Domain Transfer in", "High-Performance Computing for"
    ]
    domains = [
        "Large Language Models", "Vision-Language Grounding", "Autonomous Robotics Navigation",
        "Genome-Scale Metabolic Networks", "Quantum Error Mitigation", "Deep Reinforcement Learning",
        "Sparse Attention Mechanisms", "High-Density Energy Storage", "Graph Representation Learning",
        "Carbon Capture Optimization", "Diffusion Probabilistic Models", "Fairness in Algorithmic Decision-Making"
    ]

    for idx in range(1, 525):
        if idx <= len(paper_seeds):
            seed = paper_seeds[idx - 1]
            title, abstract, doi, arxiv, authors, venue, year, tops = seed
            source = ["openalex", "arxiv"]
        else:
            q = qualifiers[(idx * 7) % len(qualifiers)]
            d = domains[(idx * 11) % len(domains)]
            title = f"{q} {d}"
            base_abs = base_abstracts[idx % len(base_abstracts)]
            abstract = f"This paper examines modern techniques in {d}. We introduce rigorous methodology and evaluate performance across multiple benchmarks. {base_abs}"
            doi = f"10.1145/chanakya.202{idx % 6}.{10000 + idx}"
            arxiv = f"2{idx % 5:02d}{idx % 12 + 1:02d}.{10000 + idx}"
            authors = [
                f"{first_names[(idx + 1) % len(first_names)]} {last_names[(idx + 2) % len(last_names)]}",
                f"{first_names[(idx + 4) % len(first_names)]} {last_names[(idx + 5) % len(last_names)]}"
            ]
            venue = "Chanakya Academic Proceedings" if idx % 2 == 0 else "Journal of Research Systems"
            year = 2018 + (idx % 8)
            tops = [topic_list[idx % len(topic_list)].name]
            source = ["openalex"] if idx % 3 == 0 else (["arxiv"] if idx % 3 == 1 else ["rss"])

        all_paper_records.append({
            "title": title,
            "abstract": abstract,
            "canonical_doi": doi,
            "arxiv_id": arxiv,
            "openalex_id": f"W{2000000000 + idx}",
            "authors": authors,
            "venue": venue,
            "published_year": year,
            "sources": source,
            "url": f"https://doi.org/{doi}",
            "topics": tops,
        })

    # Bulk insert papers
    created_papers = []
    print("  -> Computing batch embeddings for 520+ papers...")
    text_batches = [f"{p['title']}\n{p['abstract']}" for p in all_paper_records]
    embeddings = EmbeddingService.generate_batch(text_batches)

    with transaction.atomic():
        for p_data, emb in zip(all_paper_records, embeddings):
            p = Paper.objects.filter(
                canonical_doi=p_data["canonical_doi"]
            ).first()
            if not p and p_data.get("arxiv_id"):
                p = Paper.objects.filter(arxiv_id=p_data["arxiv_id"]).first()

            if p is None:
                p = Paper.objects.create(
                    canonical_doi=p_data["canonical_doi"],
                    arxiv_id=p_data["arxiv_id"],
                    openalex_id=p_data["openalex_id"],
                    title=p_data["title"],
                    authors=p_data["authors"],
                    abstract=p_data["abstract"],
                    published_year=p_data["published_year"],
                    venue=p_data["venue"],
                    url=p_data["url"],
                    sources=p_data["sources"],
                    embedding=emb,
                    pagerank_score=0.01,
                )
                for t_name in p_data.get("topics", []):
                    t_obj = topic_objs.get(t_name)
                    if t_obj:
                        p.topics.add(t_obj)
            created_papers.append(p)

    print(f"  -> Total papers ready: {len(created_papers)} records.")

    # Create chunks for RAG Assistant (F8)
    print("  -> Creating text chunks for RAG Assistant...")
    chunk_objs = []
    chunk_texts_for_embedding = []
    chunk_meta = []

    for p in created_papers[:150]:  # Deeply chunk top 150 papers
        if p.chunks.exists():
            continue
        chunks = TextChunker.chunk_text(f"{p.title}\n\n{p.abstract}", chunk_size_words=100, overlap_words=20)
        for c_idx, c_text in enumerate(chunks):
            chunk_texts_for_embedding.append(c_text)
            chunk_meta.append((p, c_idx, c_text))

    if chunk_texts_for_embedding:
        chunk_embeddings = EmbeddingService.generate_batch(chunk_texts_for_embedding)
        for (paper, c_idx, c_text), c_emb in zip(chunk_meta, chunk_embeddings):
            chunk_objs.append(
                PaperChunk(
                    paper=paper,
                    chunk_index=c_idx,
                    chunk_text=c_text,
                    embedding=c_emb,
                )
            )
        PaperChunk.objects.bulk_create(chunk_objs)
    print(f"  -> Total text chunks active: {PaperChunk.objects.count()}.")

    # Link with research_library.ResearchResource
    print("  -> Linking papers with ResearchResource catalog...")
    staff_user = member_users[0]
    for p in created_papers:
        if p.resource_id:
            continue
        existing_res = None
        if p.canonical_doi:
            existing_res = ResearchResource.objects.filter(doi__iexact=p.canonical_doi).first()
        if not existing_res and p.arxiv_id:
            existing_res = ResearchResource.objects.filter(arxiv_id__iexact=p.arxiv_id).first()

        if existing_res:
            p.resource = existing_res
            p.save(update_fields=["resource"])
        else:
            try:
                res = ResearchResource.objects.create(
                    title=p.title,
                    description=p.abstract[:400] if p.abstract else f"Research by {p.authors_display}",
                    resource_type="link",
                    url=p.url or f"https://doi.org/{p.canonical_doi}",
                    doi=p.canonical_doi,
                    arxiv_id=p.arxiv_id,
                    uploaded_by=staff_user,
                )
                p.resource = res
                p.save(update_fields=["resource"])
            except Exception as e:
                pass

    # Build Citation Graph (1,200+ edges)
    print("  -> Generating citation graph edges and computing PageRank...")
    citation_edges = []
    paper_ids = [p.id for p in created_papers]
    existing_citations = set(PaperCitation.objects.values_list("citing_paper_id", "cited_paper_id"))
    seen_pairs = set(existing_citations)

    # Form hub papers (the early landmark papers receive many citations)
    hub_papers = paper_ids[:15]
    for p_id in paper_ids[15:]:
        # Each paper cites 2-4 landmark papers
        cites_landmarks = random.sample(hub_papers, k=random.randint(2, 4))
        for cited in cites_landmarks:
            pair = (p_id, cited)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                citation_edges.append(PaperCitation(citing_paper_id=p_id, cited_paper_id=cited))

        # Each paper cites 1-3 contemporaneous papers
        peer_pool = paper_ids[max(0, p_id - 20) : min(len(paper_ids), p_id + 20)]
        if peer_pool:
            peer_cites = random.sample(peer_pool, k=min(len(peer_pool), random.randint(1, 2)))
            for cited in peer_cites:
                if cited != p_id:
                    pair = (p_id, cited)
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        citation_edges.append(PaperCitation(citing_paper_id=p_id, cited_paper_id=cited))

    if citation_edges:
        PaperCitation.objects.bulk_create(citation_edges, ignore_conflicts=True)
    IngestionPipeline.recompute_pagerank()
    print(f"  -> Generated {len(citation_edges)} citation edges and updated PageRank.")

    # -------------------------------------------------------------
    # 4. PLANTED GROUND TRUTH INJECTION
    # -------------------------------------------------------------
    print("\n[4/7] Deliberately Injecting Planted Ground Truth...")

    ground_truth = {
        "planted_duplicates": [],
        "planted_spam_accounts": [],
        "planted_topic_spikes": [],
        "search_benchmark_queries": [],
        "recommendation_test_users": [],
        "rag_benchmark_questions": [],
    }

    # 4a. Planted Duplicates (MinHash LSH & Title Normalization variations)
    print("  -> Injecting 25 planted duplicate clusters...")
    Paper.objects.filter(
        Q(canonical_doi__contains="planted.dup") | Q(arxiv_id__startswith="2401.dup") | Q(openalex_id__startswith="W99999")
    ).delete()

    for cluster_id in range(1, 26):
        base_paper = created_papers[cluster_id * 10]
        doi_a = f"10.1145/planted.dup.a.{cluster_id}"
        doi_b = f"10.1145/planted.dup.b.{cluster_id}"
        arxiv_a = f"2401.dup{cluster_id}"
        openalex_b = f"W99999{cluster_id}"

        dup_a = Paper.objects.create(
            canonical_doi=doi_a,
            arxiv_id=arxiv_a,
            title=f"{base_paper.title}",
            abstract=base_paper.abstract,
            authors=base_paper.authors,
            venue="arXiv CoRR",
            published_year=base_paper.published_year,
            sources=["arxiv"],
            pagerank_score=0.02,
        )

        dup_b = Paper.objects.create(
            canonical_doi=doi_b,
            openalex_id=openalex_b,
            title=f"{base_paper.title} (Conference Proceedings)",
            abstract=base_paper.abstract + " Peer reviewed and cataloged.",
            authors=base_paper.authors,
            venue="OpenAlex Catalog",
            published_year=base_paper.published_year,
            sources=["openalex"],
            pagerank_score=0.03,
        )

        ground_truth["planted_duplicates"].append({
            "cluster_id": cluster_id,
            "doi_a": doi_a,
            "doi_b": doi_b,
            "primary_id": dup_a.id,
            "duplicate_id": dup_b.id,
            "title": base_paper.title,
        })

    # 4b. Planted Spam Accounts (Rapid burst posting & identical content floods)
    print("  -> Creating 5 planted spam accounts with burst activity...")
    DiscussionPost.objects.filter(author__username__startswith="spambot_promo_").delete()
    spam_users = []
    for s_idx in range(1, 6):
        spam_u, _ = User.objects.get_or_create(
            username=f"spambot_promo_{s_idx}",
            defaults={"email": f"spambot{s_idx}@external-promo.xyz", "first_name": "Spam", "last_name": "Bot"}
        )
        spam_u.set_password("SpamPass123!")
        spam_u.save()
        Profile.objects.get_or_create(user=spam_u, defaults={"role": "student", "bio": "Commercial automated account."})
        spam_users.append(spam_u)

        # Inject burst posts in last 10 minutes
        now = timezone.now()
        for p_idx in range(6):
            DiscussionPost.objects.create(
                author=spam_u,
                title=f"FREE ACADEMIC ESSAY WRITING SERVICE PROMO {s_idx}",
                content=f"Contact us now for guaranteed essay completions! Automated promo code #{s_idx}{p_idx}.",
                created_at=now - timedelta(minutes=random.randint(1, 8)),
            )

        ground_truth["planted_spam_accounts"].append({
            "user_id": spam_u.id,
            "username": spam_u.username,
            "anomaly_type": "burst_duplicate_posting",
        })

    # 4c. Planted Topic Spikes
    print("  -> Planting sudden topic spikes in 'Quantum Computing' and 'Deep Learning'...")
    spike_topics = ["Quantum Computing", "Deep Learning", "Genomics & Bioinformatics"]
    for s_topic in spike_topics:
        t_obj = topic_objs[s_topic]
        now = timezone.now()
        # Create surge of 40 events in the last 2 days
        for i in range(40):
            ActivityEvent.objects.create(
                user=random.choice(member_users),
                event_type="search",
                target_type="query",
                target_id=s_topic,
                metadata={"topic": s_topic, "topic_id": t_obj.id},
                timestamp=now - timedelta(hours=random.randint(2, 48)),
            )
        ground_truth["planted_topic_spikes"].append({
            "topic_id": t_obj.id,
            "topic_name": s_topic,
            "expected_spike": True,
        })

    # 4d. Planted Search Benchmark Queries
    search_queries = [
        ("transformer attention neural machine translation", [created_papers[0].id]),
        ("deep residual learning convolutional image recognition", [created_papers[1].id]),
        ("protein structure prediction alphafold biological sequences", [created_papers[10].id]),
        ("quantum supremacy superconducting processor qubits", [created_papers[15].id]),
        ("solid state electrolytes battery high capacity", [created_papers[18].id]),
    ]
    for q_str, expected_pids in search_queries:
        ground_truth["search_benchmark_queries"].append({
            "query": q_str,
            "expected_top_paper_ids": expected_pids,
        })

    # 4e. Planted RAG Benchmark Questions
    ground_truth["rag_benchmark_questions"] = [
        {
            "question": "How does AlphaFold predict 3D protein structures?",
            "expected_keywords": ["protein", "structure", "atomic", "alphafold", "amino acid"],
            "expected_paper_id": created_papers[10].id,
        },
        {
            "question": "What is the purpose of residual learning in deep networks?",
            "expected_keywords": ["residual", "layers", "deeper", "gradient", "image"],
            "expected_paper_id": created_papers[1].id,
        },
        {
            "question": "How do solid-state electrolytes improve battery safety and capacity?",
            "expected_keywords": ["solid-state", "battery", "electrolytes", "lithium", "capacity"],
            "expected_paper_id": created_papers[18].id,
        },
    ]

    # Save ground_truth.json
    gt_path = BASE_DIR / "data" / "ground_truth.json"
    gt_path.parent.mkdir(parents=True, exist_ok=True)
    gt_path.write_text(json.dumps(ground_truth, indent=2))
    print(f"  -> Planted ground truth saved to {gt_path}.")

    # -------------------------------------------------------------
    # 5. DISCUSSIONS & COMMUNITY ACTIVITY (2,000+ Posts & Comments)
    # -------------------------------------------------------------
    print("\n[5/7] Generating 2,000+ Community Posts and Comments...")

    post_titles = [
        "Discussion on scalability of transformer attention mechanisms",
        "Recent breakthroughs in protein design with diffusion models",
        "Reproducibility issues in deep reinforcement learning benchmarks",
        "Is quantum error mitigation sufficient for NISQ-era algorithms?",
        "Solid-state battery degradation mechanisms: Review and questions",
        "How are graph neural networks utilized in molecular docking?",
        "Single-cell transcriptomics clustering methods comparison",
        "Institutional perspectives on deploying generative AI in universities",
        "Novel algorithms for decentralized renewable grid balancing",
        "Sparse autoencoders for interpreting language model activations",
    ]

    post_objs = []
    now = timezone.now()
    active_users = member_users[1:45]

    for i in range(1, 1050):
        author = active_users[i % len(active_users)]
        base_t = post_titles[i % len(post_titles)]
        post_t = f"{base_t} [Topic #{i}]"
        post_body = f"Colleagues, I am exploring research avenues concerning {post_t}. What are your insights regarding practical implementations and dataset challenges? Please share references and findings."
        created_time = now - timedelta(days=random.randint(1, 170), hours=random.randint(0, 23))

        p = DiscussionPost(
            author=author,
            title=post_t,
            content=post_body,
            created_at=created_time,
        )
        post_objs.append(p)

    DiscussionPost.objects.bulk_create(post_objs)
    all_posts = list(DiscussionPost.objects.all().order_by("id")[:len(post_objs)])
    # Ensure post timestamps are spread over 170 days despite auto_now_add
    for p in all_posts:
        t = now - timedelta(days=random.randint(5, 170), hours=random.randint(0, 23))
        DiscussionPost.objects.filter(id=p.id).update(created_at=t)

    # Tag posts with topics and attach resources
    all_resources = list(ResearchResource.objects.all()[:150])
    for idx, p in enumerate(all_posts):
        p.tags.add(topic_list[idx % len(topic_list)])
        if idx % 3 == 0 and all_resources:
            p.resources.add(all_resources[idx % len(all_resources)])

    # Comments & Replies (1,100+ comments)
    comment_objs = []
    for i in range(1, 1150):
        post = all_posts[i % len(all_posts)]
        author = active_users[(i * 3) % len(active_users)]
        c = Comment(
            post=post,
            author=author,
            content=f"Thank you for sharing this. In our lab we observed related outcomes when evaluating this approach on departmental clusters.",
            created_at=post.created_at + timedelta(hours=random.randint(1, 48)),
        )
        comment_objs.append(c)

    Comment.objects.bulk_create(comment_objs)
    print(f"  -> Generated {len(post_objs)} posts and {len(comment_objs)} comments.")

    # -------------------------------------------------------------
    # 6. ACTIVITY EVENTS (10,000+ Saves, Views, and Searches over 6 Months)
    # -------------------------------------------------------------
    print("\n[6/7] Simulating 10,000+ Activity Events & Saved Items across 6 Months...")

    save_objs = []
    event_objs = []
    saved_tuples = set()

    for u in active_users:
        # Each member saves 8-25 papers
        num_saves = random.randint(8, 25)
        dept_topic_idx = (u.profile.department_id or 1) * 20
        candidate_pool = all_resources[dept_topic_idx : dept_topic_idx + 40] or all_resources[:40]
        chosen_resources = random.sample(candidate_pool, k=min(len(candidate_pool), num_saves))

        for res in chosen_resources:
            pair = (u.id, res.id)
            if pair not in saved_tuples:
                saved_tuples.add(pair)
                s_time = now - timedelta(days=random.randint(1, 175), hours=random.randint(0, 23))
                save_objs.append(
                    SavedResearchItem(
                        user=u,
                        resource=res,
                        private_notes="Key reference for ongoing university research proposal.",
                        saved_at=s_time,
                    )
                )

    SavedResearchItem.objects.bulk_create(save_objs, ignore_conflicts=True)

    # Update save_count on papers
    from django.db.models import F
    for s in save_objs:
        Paper.objects.filter(resource_id=s.resource_id).update(save_count=F("save_count") + 1)

    # 10,000+ Activity Events
    event_types = ["search", "view_paper", "save_paper", "create_post", "comment", "upvote"]
    weights = [0.40, 0.30, 0.12, 0.05, 0.08, 0.05]

    for e_idx in range(1, 10200):
        ev_type = random.choices(event_types, weights=weights)[0]
        u = random.choice(active_users)
        t_stamp = now - timedelta(days=random.randint(0, 180), minutes=random.randint(0, 1439))
        topic_target = random.choice(topic_list)

        meta = {"topic": topic_target.name, "topic_id": topic_target.id}
        target_id = ""

        if ev_type in ("view_paper", "save_paper"):
            paper_choice = random.choice(created_papers[:100])
            target_id = str(paper_choice.id)
            meta["title"] = paper_choice.title
        elif ev_type in ("create_post", "comment", "upvote"):
            post_choice = random.choice(all_posts[:100])
            target_id = str(post_choice.id)
            meta["title"] = post_choice.title
        else:
            target_id = topic_target.name

        event_objs.append(
            ActivityEvent(
                user=u,
                event_type=ev_type,
                target_type="topic" if ev_type == "search" else ("paper" if "paper" in ev_type else "post"),
                target_id=target_id[:100],
                metadata=meta,
                timestamp=t_stamp,
            )
        )

    ActivityEvent.objects.bulk_create(event_objs)
    print(f"  -> Generated {len(save_objs)} member saved items and {len(event_objs)} activity events.")

    # -------------------------------------------------------------
    # 7. EXPORT STAR-SCHEMA PARQUET TO MINIO & RUN ANOMALY SCANS
    # -------------------------------------------------------------
    print("\n[7/7] Running Star-Schema Parquet ETL & Precomputing Analytics...")
    paths = StarSchemaETLService.run_etl()
    print(f"  -> Parquet tables exported to MinIO and {settings.ANALYTICS_DATA_DIR}:")
    for k, v in paths.items():
        print(f"     • {k}: {v}")

    # Compute Trends
    TrendAnalyzer.calculate_topic_trends(window_days=7, baseline_days=30)
    # Detect Anomalies
    flags = AnomalyDetector.scan_for_anomalies()
    print(f"  -> Initial anomaly scan generated {len(flags)} moderation flags.")

    print("\n" + "=" * 70)
    print("SYNTHETIC SEEDING COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_synthetic_generator()
