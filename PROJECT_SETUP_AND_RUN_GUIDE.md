# Chanakya Research Commons — Complete Setup & Reproduction Guide

This guide provides end-to-end instructions for configuring, initializing, running, and evaluating the **Chanakya Research Commons** platform on a clean machine.

---

## 1. System Requirements & Prerequisites

- **Operating System:** macOS 14+, Ubuntu 22.04 LTS+, or Windows with WSL2
- **Python Version:** Python 3.12+ (strictly tested with Python 3.12.7)
- **Database Engine:** PostgreSQL 16+ with the **`pgvector`** extension enabled
- **In-Memory OLAP Engine:** DuckDB 1.2.0 (bundled in Python dependencies)
- **Disk Space:** Minimum 2 GB free disk space (for PostgreSQL data, embeddings, and raw data lake storage)

---

## 2. Environment Setup & Dependency Installation

### Step 2.1: Clone Repository & Create Virtual Environment
```bash
# Clone the repository
git clone https://github.com/indian-command/Data-Mining-and-warehouse-project-1.git
cd Data-Mining-and-warehouse-project-1

# Create Python 3.12 virtual environment
python3.12 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Windows WSL / Git Bash
# source .venv/bin/activate.fish  # If using fish shell
```

### Step 2.2: Install Required Python Packages
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

*Note on SentenceTransformers / PyTorch:* The system uses the lightweight `sentence-transformers/all-MiniLM-L6-v2` model (384-dimensional dense vectors) which runs efficiently on standard CPU architectures without requiring dedicated GPUs.

---

## 3. Database Initialization & Configuration

### Step 3.1: Create PostgreSQL Database with `pgvector`
Ensure PostgreSQL 16 is running locally, then execute:
```bash
# Create database
createdb chanakya_commons

# Enable pgvector extension inside the database
psql -d chanakya_commons -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Step 3.2: Configure Environment Variables
Create a `.env` file in the project root directory (or use default development fallbacks):
```ini
DEBUG=True
SECRET_KEY=django-insecure-chanakya-dmw-research-commons-2026-key
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/chanakya_commons
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
```

### Step 3.3: Apply Database Migrations
Apply all schema migrations across all installed apps:
```bash
python manage.py migrate
```

---

## 4. Data Seeding & Vector Embedding Pipeline

### Step 4.1: Seed Campus Data & Benchmark Ground Truth
Seed the complete academic campus dataset (14 departments, 20 topics, 227 users, 642 base papers, 2,292 citations, discussions, and 10,400+ historical activity events):
```bash
python scripts/seed_data.py
```

### Step 4.2: Generate Dense Semantic Vector Embeddings
Ensure 100% of papers have 384-dimensional `pgvector` embeddings indexed in PostgreSQL:
```bash
python manage.py generate_embeddings
```

---

## 5. Running the Application & Background Services

### Step 5.1: Run Incremental Ingestion Background Scheduler
The background scheduler performs incremental scholarly data harvesting from OpenAlex and arXiv with rotating watermarks, storing raw payloads and generating embeddings automatically:

**Option A: Single-Batch Execution (Verification)**
```bash
python manage.py run_scheduler --limit 1
```

**Option B: Continuous Background Daemon (Production Mode)**
```bash
python manage.py run_scheduler --daemon --interval 300
```
*(Runs continuously, waking every 300 seconds to poll external sources, update watermarks, and log execution history to `IngestionRunLog`)*.

### Step 5.2: Start Django Web Application Server
In a separate terminal (with `.venv` active):
```bash
python manage.py runserver 0.0.0.0:8080
```
Open your browser and navigate to: **`http://localhost:8080/`**

---

## 6. Running Test Suites & Quantitative Benchmarks

### Step 6.1: Run Full Unit Test Suite (63 Tests)
```bash
python manage.py test --verbosity=1
```
*Expected Output: `Ran 63 tests in ~12s ... OK`*

### Step 6.2: Run Empirical Quantitative Benchmark Suite
Evaluates Search NDCG@10, Duplicate Resolution F1, Recommendation HitRate/MRR, Anomaly Detection Recall, and RAG Groundedness against `data/ground_truth.json`:
```bash
python scripts/evaluate.py
```
*Expected Output:*
- BM1 Search NDCG@10: `1.0000` (+100.0% gain over keyword baseline)
- BM2 Duplicate Resolution: `25/25` merged, Precision: `1.0000`, Recall: `1.0000`, F1: `1.0000`
- BM3 Recommendations HitRate@10: `0.5000` (+45.0% gain over popularity baseline)
- BM4 Anomaly Detection: Spam Accounts F1: `1.0000` (5/5), Topic Spikes F1: `1.0000` (3/3)
- BM5 RAG Assistant: Retrieval Recall@5: `1.0000`, Citation Inclusion: `1.0000`, Faithfulness: `0.8000`

### Step 6.3: Run Complete Functional Audit Runner
Simulates HTTP client interaction across all 9 requirements (F1–F9) and 4 end-to-end integration workflows:
```bash
python scripts/audit_runner.py
```
*Expected Output: `ALL AUDIT TESTS COMPLETED! Saved to audit_evidence/audit_test_results.json`*

---

## 7. Pre-Configured Test Credentials

| Role | Username | Password | Purpose / Access Permissions |
| :--- | :--- | :--- | :--- |
| **Student** | `student1` | `password123` | Personal library, discussions, feed, recommendations, research assistant. Blocked from analytics/trends. |
| **Faculty** | `faculty1` | `password123` | Full access to discussions, peer reviews, library, departmental trends, and institutional analytics. |
| **Admin** | `admin` | `adminpass123` | Superuser privileges: moderation queue, anomaly review, raw ingestion management, star schema OLAP export. |

---

## 8. Directory & File Reference

- `papers/`: External scholarly ingestion, OpenAlex/arXiv API clients, raw data lake storage, and `IngestionRunLog`.
- `unified_search/`: 4-panel federated search, hybrid BM25 + pgvector + PageRank, and MinHash LSH entity resolution.
- `recommendations/`: Vector centroid cosine similarity, collaborative filtering co-save matrix, and PageRank cold-start fallback.
- `trends/`: Statistical Z-score topic spike detection, sliding-window rate anomaly detector, and admin moderation queue.
- `research_assistant/`: RAG chunk retrieval, context assembly, and grounded prompt synthesis with bracketed citations.
- `institutional_analytics/`: DuckDB in-memory OLAP engine, star schema ETL (`fact_activity`), and department drill-down views.
- `final_evidence/`: Verified screenshots, benchmark outputs, scheduler logs, and audit test JSON results.
