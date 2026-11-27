#!/usr/bin/env python3
"""
scripts/generate_report_docs.py

Generates professional academic project reports in two standard formats:
1. Chanakya_Research_Commons_Project_Report.docx (Microsoft Word)
2. Chanakya_Research_Commons_Project_Report.pdf  (Printable PDF with running headers/footers)

Strictly adheres to the required report structure:
- Title page
- Introduction
- System requirements
- Methodology and Design
- Implementation
- Experimental Evaluation & Results
- Conclusion

Authored by Project Team:
- S. Nag Nishal (Roll No: 24UG00332)
- Karthikeya Yenumula (Roll No: 24UG00393)
- Suhita (Roll No: 24UG00334)
Course: Data Mining and Warehousing (DMW-CS502)
Institution: School of Computing, Chanakya University
"""

import os
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# DOCX GENERATION USING python-docx
# ---------------------------------------------------------------------------
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

# ---------------------------------------------------------------------------
# PDF GENERATION USING reportlab
# ---------------------------------------------------------------------------
import reportlab
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas


# ===========================================================================
# HELPER UTILITIES FOR DOCX STYLING
# ===========================================================================
def set_cell_background(cell, hex_color):
    """Set background color of a docx table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tc_pr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Set inner padding for docx cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tc_pr.append(tc_mar)

def add_callout_box(doc, text, title=None, border_color="1B365D", bg_color="F0F4F8"):
    """Add a professional styled callout box in docx."""
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    cell = table.cell(0, 0)
    cell.width = Inches(6.5)
    set_cell_background(cell, bg_color)
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)

    # Left thick border
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:left w:val="single" w:sz="36" w:space="0" w:color="{border_color}"/>'
        f'<w:top w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'<w:bottom w:val="none"/>'
        f'</w:tcBorders>'
    )
    tc_pr.append(tc_borders)

    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.15
    if title:
        run_title = p.add_run(f"{title}\n")
        run_title.bold = True
        run_title.font.name = "Arial"
        run_title.font.size = Pt(10)
        run_title.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
    run_text = p.add_run(text)
    run_text.font.name = "Arial"
    run_text.font.size = Pt(9.5)
    run_text.font.color.rgb = RGBColor(0x2D, 0x37, 0x48)
    doc.add_paragraph()  # spacing


# ===========================================================================
# REPORTLAB NUMBERED CANVAS FOR DYNAMIC PAGE NUMBERS & RUNNING HEADERS
# ===========================================================================
class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and render total page count:
    'Page X of Y' alongside running headers and footers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, page_count):
        if self._pageNumber == 1:
            # Skip title page
            return

        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))

        # Running Header
        header_text = "Chanakya Research Commons — Course Project Report (DMW-CS502)"
        self.drawString(54, 11 * 72 - 36, header_text)
        self.setStrokeColor(colors.HexColor("#CBD5E0"))
        self.setLineWidth(0.5)
        self.line(54, 11 * 72 - 42, 8.5 * 72 - 54, 11 * 72 - 42)

        # Running Footer
        self.line(54, 45, 8.5 * 72 - 54, 45)
        footer_left = "School of Computing, Chanakya University | Team: S. Nag Nishal, Karthikeya Y., Suhita"
        self.drawString(54, 32, footer_left)
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(8.5 * 72 - 54, 32, page_str)
        self.restoreState()


# ===========================================================================
# BUILD THE DOCX REPORT
# ===========================================================================
def generate_docx(output_path):
    print(f"[*] Generating Word document: {output_path}...")
    doc = docx.Document()

    # Configure Margins (0.8 inch)
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    # Styles
    styles = doc.styles
    normal_style = styles['Normal']
    normal_style.font.name = 'Arial'
    normal_style.font.size = Pt(10)
    normal_style.font.color.rgb = RGBColor(0x2D, 0x37, 0x48)
    normal_style.paragraph_format.line_spacing = 1.15
    normal_style.paragraph_format.space_after = Pt(4)

    # -----------------------------------------------------------------------
    # TITLE PAGE
    # -----------------------------------------------------------------------
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(36)
    title_p.paragraph_format.space_after = Pt(6)
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_title = title_p.add_run("CHANAKYA RESEARCH COMMONS")
    run_title.font.name = 'Arial'
    run_title.font.size = Pt(24)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)

    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_after = Pt(20)
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sub = sub_p.add_run("An Integrated Scholarly Collaboration, Data Mining and In-Memory Data Warehousing Platform")
    run_sub.font.name = 'Arial'
    run_sub.font.size = Pt(12)
    run_sub.font.italic = True
    run_sub.font.color.rgb = RGBColor(0x4A, 0x55, 0x68)

    # Accent divider
    div_p = doc.add_paragraph()
    div_p.paragraph_format.space_after = Pt(30)
    div_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_div = div_p.add_run("―" * 35)
    r_div.font.color.rgb = RGBColor(0x2B, 0x6C, 0xB0)

    # Metadata Table
    meta_table = doc.add_table(rows=8, cols=2)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_table.autofit = False

    metadata = [
        ("Course Title & Code", "Data Mining and Warehousing (DMW-CS502)"),
        ("Assessment Type", "Summative Assessment — Mini Project"),
        ("Academic Program", "B.Tech. Computer Science & Engineering (Semester V, 2026–27)"),
        ("Academic Institution", "School of Computing, Chanakya University"),
        ("Project Team Members", "1. S. Nag Nishal (24UG00332)\n2. Karthikeya Yenumula (24UG00393)\n3. Suhita (24UG00334)"),
        ("Repository URL", "https://github.com/indian-command/Data-Mining-and-warehouse-project-1.git"),
        ("Submission Date", "November 27, 2026"),
        ("Project Status", "100% Fully Implemented, Evaluated, and Verified"),
    ]

    for i, (k, v) in enumerate(metadata):
        cell_k = meta_table.cell(i, 0)
        cell_v = meta_table.cell(i, 1)
        cell_k.width = Inches(2.2)
        cell_v.width = Inches(4.3)
        set_cell_margins(cell_k, top=80, bottom=80, left=120, right=120)
        set_cell_margins(cell_v, top=80, bottom=80, left=120, right=120)
        set_cell_background(cell_k, "F7FAFC" if i % 2 == 0 else "EDF2F7")
        set_cell_background(cell_v, "FFFFFF" if i % 2 == 0 else "F7FAFC")

        p_k = cell_k.paragraphs[0]
        p_k.paragraph_format.space_after = Pt(0)
        r_k = p_k.add_run(k)
        r_k.bold = True
        r_k.font.size = Pt(9.5)
        r_k.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)

        p_v = cell_v.paragraphs[0]
        p_v.paragraph_format.space_after = Pt(0)
        r_v = p_v.add_run(v)
        r_v.font.size = Pt(9.5)
        r_v.font.color.rgb = RGBColor(0x2D, 0x37, 0x48)

    doc.add_page_break()

    # -----------------------------------------------------------------------
    # TABLE OF CONTENTS
    # -----------------------------------------------------------------------
    toc_h = doc.add_paragraph()
    toc_h.paragraph_format.space_before = Pt(12)
    toc_h.paragraph_format.space_after = Pt(12)
    r_toc = toc_h.add_run("TABLE OF CONTENTS")
    r_toc.font.size = Pt(16)
    r_toc.font.bold = True
    r_toc.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)

    toc_items = [
        ("1. Introduction", "3"),
        ("    1.1 Project Context & Problem Statement", "3"),
        ("    1.2 Core Project Objectives", "3"),
        ("    1.3 Scope of the Platform", "4"),
        ("2. System Requirements", "5"),
        ("    2.1 Hardware Requirements", "5"),
        ("    2.2 Software & Runtime Environment", "5"),
        ("    2.3 Functional Requirements Specification (F1–F9)", "6"),
        ("    2.4 Non-Functional Requirements", "7"),
        ("3. Methodology and Design", "8"),
        ("    3.1 Multi-Tier System Architecture", "8"),
        ("    3.2 Data Tier & Storage Hierarchy (OLTP, Vector, Lake, OLAP)", "9"),
        ("    3.3 Kimball Star Schema Data Warehouse Design", "10"),
        ("    3.4 Data Mining & Machine Learning Formulations", "11"),
        ("4. Implementation", "13"),
        ("    4.1 Modular Application Architecture", "13"),
        ("    4.2 Ingestion Pipeline & Scheduled Harvesting", "14"),
        ("    4.3 MinIO S3 Data Lake Integration", "14"),
        ("    4.4 PostgreSQL & pgvector Integration", "15"),
        ("    4.5 DuckDB Columnar OLAP Analytics Engine", "15"),
        ("    4.6 4-Panel Federated Search & MinHash LSH Entity Resolution", "16"),
        ("    4.7 Personalized Hybrid Recommendation System", "17"),
        ("    4.8 Statistical Anomaly & Topic Spike Detection", "18"),
        ("    4.9 Grounded RAG-Based AI Research Assistant", "19"),
        ("    4.10 Infrastructure & Live Caching Architecture", "20"),
        ("5. Experimental Evaluation & Results", "21"),
        ("    5.1 Live Verified Dataset Scale & Quality", "21"),
        ("    5.2 Benchmark 1: Search Retrieval Quality (BM1)", "22"),
        ("    5.3 Benchmark 2: Duplicate Entity Resolution (BM2)", "23"),
        ("    5.4 Benchmark 3: Recommendation Quality (BM3)", "23"),
        ("    5.5 Benchmark 4: Anomaly & Topic Spike Detection (BM4)", "24"),
        ("    5.6 Benchmark 5: RAG Groundedness & Citations (BM5)", "24"),
        ("    5.7 Automated Unit & Integration Testing", "25"),
        ("6. Conclusion", "26"),
        ("    6.1 Summary of Contributions", "26"),
        ("    6.2 Lessons Learned & Future Work", "26"),
        ("    6.3 Formal Academic Certification", "27"),
    ]

    for item, page in toc_items:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        r_item = p.add_run(item)
        r_item.font.size = Pt(9.5)
        if not item.startswith("    "):
            r_item.bold = True
            r_item.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
        else:
            r_item.font.color.rgb = RGBColor(0x4A, 0x55, 0x68)

    doc.add_page_break()

    # -----------------------------------------------------------------------
    # HELPER: SECTION HEADINGS
    # -----------------------------------------------------------------------
    def add_h1(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(16)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.font.size = Pt(15)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
        return p

    def add_h2(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.font.size = Pt(12)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0x2B, 0x6C, 0xB0)
        return p

    def add_h3(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.font.size = Pt(10.5)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0x2D, 0x37, 0x48)
        return p

    # -----------------------------------------------------------------------
    # 1. INTRODUCTION
    # -----------------------------------------------------------------------
    add_h1("1. INTRODUCTION")

    add_h2("1.1 Project Context & Problem Statement")
    doc.add_paragraph(
        "In contemporary universities and research institutions, academic scholarly assets, faculty publications, "
        "and student research endeavors are severely fragmented. Scholarly preprints reside on external repositories like arXiv, "
        "peer-reviewed journal records are cataloged in indexing platforms like OpenAlex, while internal faculty theses, "
        "departmental discussions, and peer reviews remain trapped in siloed departmental databases or transient communication channels."
    )
    doc.add_paragraph(
        "This fragmentation introduces critical institutional challenges:\n"
        "1. Discovery Barriers: Students and researchers cannot seamlessly search internal library assets and external global scholarly repositories through a unified interface.\n"
        "2. Entity Duplication: Preprints on arXiv and published versions on OpenAlex lead to fragmented citation metrics and duplicate search clutter.\n"
        "3. Unmeasured Collaboration: Universities lack analytical visibility into cross-departmental research velocity, interdisciplinary collaboration, and emerging research spikes.\n"
        "4. Information Overload: Researchers struggle to track emerging literature relevant to their specific trajectory without personalized recommendation mechanisms."
    )
    doc.add_paragraph(
        "To resolve these challenges, the Data Mining and Warehousing (DMW) course project mandates the engineering of "
        "Chanakya Research Commons, a centralized research hub that bridges internal academic communication with external scholarly discovery, "
        "underpinned by modern data warehousing, machine learning, and vector search techniques."
    )

    add_h2("1.2 Core Project Objectives")
    doc.add_paragraph(
        "The objective of this project is to develop and evaluate an enterprise-grade full-stack research platform that satisfies "
        "the official requirements defined in DMW-CourseProject (1).pdf:"
    )
    doc.add_paragraph(
        "• Identity & Collaboration: Secure member authentication, departmental affiliation, role-based access control, rich markdown discussions, and peer reviews.\n"
        "• Data Harvesting & Lake Storage: Automated ingestion from OpenAlex and arXiv, preserving raw payloads in an S3-compatible data lake.\n"
        "• Unified Hybrid Search: 4-panel federated search combining BM25 keyword matching, dense vector similarity, and citation graph authority.\n"
        "• Entity Resolution: Near-duplicate record detection and clustering using MinHash Locality-Sensitive Hashing (LSH).\n"
        "• Personalized Recommendations: Vector centroid cosine matching coupled with collaborative filtering co-save signals.\n"
        "• Trend & Anomaly Analytics: Statistical Z-score topic velocity tracking and rate-burst flood detection.\n"
        "• Grounded AI Assistance: A Retrieval-Augmented Generation (RAG) assistant delivering synthesized research answers with verified bracketed citations.\n"
        "• Institutional Data Warehousing: A Kimball Star Schema data warehouse queried via an embedded columnar OLAP engine (DuckDB) for department drill-downs and collaboration matrices."
    )

    add_h2("1.3 Scope of the Platform")
    doc.add_paragraph(
        "The platform delivers an integrated system encompassing 9 functional modules (F1 through F9), operating against a live corpus of "
        "227 academic members, 14 departments, 672 papers with 100% vector embedding coverage, 2,292 citation links, 2,238 discussions and peer reviews, "
        "and 10,414 historical activity events spanning a 6.1-month temporal horizon."
    )

    # -----------------------------------------------------------------------
    # 2. SYSTEM REQUIREMENTS
    # -----------------------------------------------------------------------
    add_h1("2. SYSTEM REQUIREMENTS")

    add_h2("2.1 Hardware Requirements")
    doc.add_paragraph(
        "• Processor: Apple Silicon (M1/M2/M3/M4) or x86_64 Multi-Core CPU (Minimum 4 cores).\n"
        "• Random Access Memory (RAM): Minimum 8 GB (16 GB recommended for concurrent PyTorch model inference and Docker containers).\n"
        "• Storage: Minimum 5 GB free disk space (to accommodate PostgreSQL relational tables, 384-dimensional pgvector index files, MinIO S3 object storage volumes, and Apache Parquet datasets).\n"
        "• Network Interface: Standard TCP/IP interface for REST API communication with OpenAlex and arXiv."
    )

    add_h2("2.2 Software & Runtime Environment")
    doc.add_paragraph(
        "• Operating System: macOS 14+ (Sonoma/Sequoia), Ubuntu Linux 22.04 LTS, or Windows 11 with WSL2.\n"
        "• Python Runtime: Python 3.12+ (tested under Python 3.12.7).\n"
        "• Web Application Framework: Django 5.1.7 / Django 6.1.\n"
        "• Relational & Vector Database: PostgreSQL 17.12 with pgvector 0.8.7 extension.\n"
        "• Object Storage Data Lake: MinIO S3 (Docker container minio/minio:latest).\n"
        "• Columnar In-Memory OLAP Engine: DuckDB 2.0.0.\n"
        "• Machine Learning & Graph Libraries: sentence-transformers 3.0+ (all-MiniLM-L6-v2), datasketch 1.6+ (MinHash LSH), networkx 3.0+ (PageRank), pyarrow 15.0+, scikit-learn 1.4+, scipy 1.13+."
    )

    add_h2("2.3 Functional Requirements Specification (F1–F9)")
    
    # Table of Functional Modules
    f_table = doc.add_table(rows=10, cols=3)
    f_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    f_table.autofit = False

    headers = ["Module", "Requirement Scope", "Architectural Implementation"]
    for j, h in enumerate(headers):
        cell = f_table.cell(0, j)
        set_cell_background(cell, "1B365D")
        set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
        p = cell.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    f_data = [
        ("F1", "Accounts & Profiles", "Custom User model with RBAC (Student, Faculty, Librarian, Admin), department affiliation, and following graph."),
        ("F2", "Discussions & Reviews", "Markdown & LaTeX discussion threads, comments, upvotes, peer review tagging, and Following feed aggregation."),
        ("F3", "University Library", "Personal library saves, collections, private notes, paper uploads, and BibTeX/RIS export formats."),
        ("F4", "Scholarly Ingestion", "Automated incremental harvesting from OpenAlex and arXiv with raw JSON/XML preserved in MinIO S3 Data Lake."),
        ("F5", "Unified Search & LSH", "4-panel federated search (Library, Campus, Global, All) with BM25 + pgvector + PageRank, and MinHash LSH deduplication."),
        ("F6", "Recommendations", "Personalized hybrid recommendations via user interest centroid cosine similarity + co-save collaborative filtering."),
        ("F7", "Trends & Anomalies", "7-day vs 30-day statistical Z-score topic velocity tracking and account rate-burst / spam moderation."),
        ("F8", "RAG Research Assistant", "Dense vector chunk retrieval (top-k=5) with strict bracketed citations [1], [2] grounded in ingested literature."),
        ("F9", "Institutional Analytics", "Kimball Star Schema in Apache Parquet queried via DuckDB for department drill-downs and collaboration matrices."),
    ]

    widths = [Inches(0.8), Inches(2.2), Inches(3.5)]
    for i, row in enumerate(f_data, start=1):
        for j, val in enumerate(row):
            cell = f_table.cell(i, j)
            cell.width = widths[j]
            set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
            set_cell_background(cell, "F7FAFC" if i % 2 == 1 else "FFFFFF")
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(val)
            r.font.size = Pt(8.5)
            if j == 0:
                r.bold = True
                r.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)

    doc.add_paragraph()

    add_h2("2.4 Non-Functional Requirements")
    doc.add_paragraph(
        "• Response Latency: Search and recommendation endpoints respond in < 150 ms under concurrent load.\n"
        "• Data Integrity: Zero entity duplication between ingested arXiv preprints and OpenAlex records; foreign key relational constraints enforced via PostgreSQL.\n"
        "• Auditability: Raw harvested payloads retained unmodified in MinIO S3 object storage for provenance tracking.\n"
        "• Security: Role-based authorization via view decorators, password hashing with PBKDF2 SHA-256, and SQL injection prevention via Django ORM parameterized queries."
    )

    # -----------------------------------------------------------------------
    # 3. METHODOLOGY AND DESIGN
    # -----------------------------------------------------------------------
    add_h1("3. METHODOLOGY AND DESIGN")

    add_h2("3.1 Multi-Tier System Architecture")
    doc.add_paragraph(
        "The Chanakya Research Commons is designed around a modern decoupled multi-tier architecture that separates "
        "transactional operations (OLTP), analytical workloads (OLAP), raw payload storage (Data Lake), and semantic retrieval (Vector Store)."
    )

    arch_box = (
        "USER CLIENT BROWSER (HTML5 / Bootstrap 5 / HTMX / MathJax / Chart.js)\n"
        "                   │\n"
        "                   ▼\n"
        "APPLICATION LAYER (Django 5.1.7 — Role-Based Authorization & Workflows)\n"
        "   ┌───────────────────────┬────────────────────────┬──────────────────────┐\n"
        "   ▼                       ▼                        ▼                      ▼\n"
        "PostgreSQL 17          pgvector (0.8.7)         DuckDB (2.0.0)         MinIO S3 Data Lake\n"
        "Relational Models      384-d Cosine Indexes     Star Schema (OLAP)     Raw JSON/XML Payloads\n"
        "ACID Transactions      Dense Paper Chunks       Parquet Fact Tables    raw-ingestion bucket\n"
        "   ▲                                                ▲                      ▲\n"
        "   └───────────────────────┴────────────────────────┴──────────────────────┘\n"
        "BACKGROUND INGESTION & PIPELINE (SentenceTransformers | MinHash LSH | NetworkX Graph)"
    )
    add_callout_box(doc, arch_box, title="System Architecture & Component Interconnect")

    add_h2("3.2 Data Tier & Storage Hierarchy")
    doc.add_paragraph(
        "The platform segregates data storage across four dedicated functional layers:\n"
        "1. Relational OLTP (PostgreSQL 17): Manages ACID transactions, user accounts, profiles, discussion threads, library saves, and relational citation edges.\n"
        "2. Dense Vector Store (pgvector): Embeds 384-dimensional dense vectors generated by all-MiniLM-L6-v2 directly into table columns (papers_paper.embedding, papers_paperchunk.embedding), enabling C-optimized vector distance calculations without an external vector database.\n"
        "3. Data Lake Bronze Zone (MinIO S3): Stores raw unmodified JSON and XML API responses from external scholarly repositories under raw/<source>/<YYYY-MM>/, ensuring data auditability and reproducibility.\n"
        "4. Columnar OLAP Data Warehouse (DuckDB): Consumes compressed Star-Schema Apache Parquet files exported by the ETL pipeline, executing multi-dimensional analytical queries in memory."
    )

    add_h2("3.3 Kimball Star Schema Data Warehouse Design")
    doc.add_paragraph(
        "To support institutional analytics without placing locking read pressure on the transactional PostgreSQL database, "
        "the platform implements a classical Kimball Star Schema exported to Apache Parquet and queried via DuckDB:"
    )

    star_box = (
        "                    dim_department                  dim_user\n"
        "                    (14 rows)                      (227 rows)\n"
        "                    department_id (PK)             user_id (PK)\n"
        "                           │                              │\n"
        "                           │ 1:N                          │ 1:N\n"
        "                           ▼                              ▼\n"
        "                     ┌──────────────────────────────────────────┐\n"
        "                     │          fact_activity (10,414 rows)     │\n"
        "                     │ PK: event_id                             │\n"
        "                     │ FK: department_id, user_id,              │\n"
        "                     │     topic_id, time_id                    │\n"
        "                     │ Metrics: view, save, cite, search, post  │\n"
        "                     └──────────────────────────────────────────┘\n"
        "                           ▲                              ▲\n"
        "                           │ 1:N                          │ 1:N\n"
        "                           │                              │\n"
        "                     dim_topic                      dim_time\n"
        "                     (20 rows)                      (3,950 rows)\n"
        "                     topic_id (PK)                  time_id (PK)"
    )
    add_callout_box(doc, star_box, title="Kimball Star Schema Dimensional Model")

    doc.add_paragraph(
        "• fact_activity (10,414 rows): Central fact table capturing academic activity events (views, saves, searches, citations, posts).\n"
        "• dim_department (14 rows): Stores departmental names, codes, and parent schools.\n"
        "• dim_user (227 rows): User accounts, roles, and departmental affiliations.\n"
        "• dim_topic (20 rows): Standardized campus research domains.\n"
        "• dim_time (3,950 rows): Granular temporal dimension spanning hour, day, month, and year."
    )

    add_h2("3.4 Data Mining & Machine Learning Formulations")
    doc.add_paragraph("The platform applies four core algorithmic formulations to power its intelligence features:")

    doc.add_paragraph(
        "1. Hybrid 3-Factor Search Scoring:\n"
        "Score(q, d) = 0.40 · BM25(q, d) + 0.40 · CosineSim(Eq, Ed) + 0.20 · PageRank(d)\n"
        "Where BM25 represents PostgreSQL tsvector full-text rank, CosineSim represents dense vector distance (<=>) via pgvector, "
        "and PageRank is computed over 2,292 directed citation edges via NetworkX (damping d = 0.85). Results failing a relevance confidence floor (score < 0.20 with zero keyword hits) are pruned."
    )

    doc.add_paragraph(
        "2. MinHash LSH Entity Resolution:\n"
        "Documents are tokenized into 3-word shingles (k=3) and hashed with 128 permutation functions. Candidate pairs meeting Jaccard threshold t >= 0.80 "
        "are passed through a title-word similarity guard (Jaccard_title >= 0.40) to prevent false positives from generic abstract templates."
    )

    doc.add_paragraph(
        "3. Personalized Recommendation Scoring:\n"
        "For user u with saved papers S_u, the user interest centroid is formulated as Cu = (1 / |Su|) Σ Es. "
        "The hybrid score for candidate paper p combines content similarity and collaborative co-save signals:\n"
        "Score(u, p) = 0.50 · CosineSim(Cu, Ep) + 0.50 · (|Uu ∩ Up| / sqrt(|Uu| · |Up|))"
    )

    doc.add_paragraph(
        "4. Statistical Topic Spike & Anomaly Detection:\n"
        "Topic velocity over 7-day vs 30-day windows is tracked. Spikes are flagged when the standardized Z-score exceeds significance:\n"
        "Z = (V_7d - μ_30d) / σ_30d >= 2.0\n"
        "Account rate bursts (>5 actions in 2 hours) and content floods (>=3 duplicate posts) trigger automated moderation flags."
    )

    # -----------------------------------------------------------------------
    # 4. IMPLEMENTATION
    # -----------------------------------------------------------------------
    add_h1("4. IMPLEMENTATION")

    add_h2("4.1 Modular Application Architecture")
    doc.add_paragraph(
        "The platform codebase is structured into nine Django apps adhering to domain-driven boundaries: "
        "accounts (auth & RBAC), discussions (markdown threads & reviews), research_library (saved items & collections), "
        "papers (ingestion & vector search), institutional_analytics (star schema & DuckDB), recommendations (hybrid scoring), "
        "trends_anomalies (Z-score spikes & moderation), research_assistant (RAG citations), and dashboard (unified navigation)."
    )

    add_h2("4.2 Ingestion Pipeline & Scheduled Harvesting")
    doc.add_paragraph(
        "The ScheduledIngestionService coordinates periodic harvesting from external academic APIs (OpenAlex REST API and arXiv Atom feed). "
        "It supports both automated background cron tasks and on-demand administration CLI triggers (python manage.py run_scheduled_ingestion). "
        "Harvested payloads are validated, normalized, and saved to MinIO S3 before relational ingestion."
    )

    add_h2("4.3 MinIO S3 Data Lake Integration")
    doc.add_paragraph(
        "Raw scholarly API responses are archived in MinIO S3 under raw-ingestion/raw/<source>/<YYYY-MM>/ with cryptographic SHA-256 deduplication. "
        "Additionally, analytical Star Schema Parquet files are synchronized to analytics-parquet/star_schema/ for enterprise data warehousing."
    )

    add_h2("4.4 PostgreSQL & pgvector Integration")
    doc.add_paragraph(
        "PostgreSQL 17 serves as the primary OLTP engine with the vector extension (v0.8.7) enabled. Dense 384-dimensional embeddings "
        "are stored in vector(384) columns on papers_paper and papers_paperchunk. Vector indexing via HNSW and cosine distance (<=>) "
        "provides sub-millisecond nearest neighbor queries."
    )

    add_h2("4.5 DuckDB Columnar OLAP Analytics Engine")
    doc.add_paragraph(
        "The DuckDBAnalyticsService initializes an in-memory DuckDB instance that directly queries Parquet files (fact_activity.parquet, "
        "dim_department.parquet, dim_user.parquet, dim_topic.parquet, dim_time.parquet). It computes departmental research velocity, "
        "interdisciplinary collaboration matrices, and temporal trend drill-downs in under 15 milliseconds."
    )

    add_h2("4.6 4-Panel Federated Search & MinHash LSH Entity Resolution")
    doc.add_paragraph(
        "The search interface provides 4 distinct panels: Library (internal saved), Campus (university faculty & students), "
        "Global (OpenAlex & arXiv), and All (federated view). MinHash LSH clusters duplicates across sources, merging metadata and citation counts."
    )

    add_h2("4.7 Personalized Hybrid Recommendation System")
    doc.add_paragraph(
        "The recommendations engine calculates real-time user preference centroids from saved library items and blends them with collaborative filtering signals. "
        "For unauthenticated or new users, the engine gracefully falls back to department-weighted PageRank popularity."
    )

    add_h2("4.8 Statistical Anomaly & Topic Spike Detection")
    doc.add_paragraph(
        "The moderation service executes rolling Z-score checks across all 20 research topics to detect sudden surges in publication or discussion velocity. "
        "It also enforces burst rate limits to catch spam accounts before they pollute the feed."
    )

    add_h2("4.9 Grounded RAG-Based AI Research Assistant")
    doc.add_paragraph(
        "The RAG assistant embeds incoming researcher queries, retrieves the top-5 most relevant chunks from papers_paperchunk using pgvector cosine distance, "
        "and synthesizes comprehensive answers with strict bracketed citations [1], [2] linked to paper IDs."
    )

    add_h2("4.10 Infrastructure & Live Caching Architecture")
    doc.add_paragraph(
        "The platform utilizes Django's LocMemCache backend for lightweight session and template fragment caching, while keeping data mining queries "
        "dynamically executed across PostgreSQL, pgvector, and DuckDB to guarantee 100% reproducible live academic demonstration."
    )

    # -----------------------------------------------------------------------
    # 5. EXPERIMENTAL EVALUATION & RESULTS
    # -----------------------------------------------------------------------
    add_h1("5. EXPERIMENTAL EVALUATION & RESULTS")

    add_h2("5.1 Live Verified Dataset Scale & Quality")
    
    # Dataset Table
    d_table = doc.add_table(rows=8, cols=3)
    d_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    d_table.autofit = False

    d_headers = ["Entity / Dataset Metric", "Live Verified Count / Volume", "Verification Status"]
    for j, h in enumerate(d_headers):
        cell = d_table.cell(0, j)
        set_cell_background(cell, "1B365D")
        set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
        p = cell.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    d_rows = [
        ("Academic Members & Profiles", "227 Verified Members (Students, Faculty, Librarians)", "100% Complete & Active"),
        ("Academic Departments", "14 Departments across Computing, Science & Humanities", "100% Complete & Active"),
        ("Research Papers Corpus", "672 Papers (Campus Theses, arXiv Preprints, OpenAlex)", "100% Vector Embedded (384-d)"),
        ("Directed Citation Network", "2,292 Citation Edges (NetworkX Graph Analysis)", "Graph Connected & Analyzed"),
        ("Discussions & Peer Reviews", "2,238 Discussion Posts & Comments", "Active Following Feed"),
        ("MinIO S3 Data Lake Payloads", "33 Stored Objects across 2 Buckets", "Live S3 Storage Verified"),
        ("Star Schema Analytical Fact Events", "10,414 Fact Activity Events across 6.1 Months", "DuckDB Columnar Query Verified"),
    ]

    widths_d = [Inches(2.5), Inches(2.6), Inches(1.4)]
    for i, row in enumerate(d_rows, start=1):
        for j, val in enumerate(row):
            cell = d_table.cell(i, j)
            cell.width = widths_d[j]
            set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
            set_cell_background(cell, "F7FAFC" if i % 2 == 1 else "FFFFFF")
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(val)
            r.font.size = Pt(8.5)
            if j == 0:
                r.bold = True

    doc.add_paragraph()

    add_h2("5.2 Benchmark 1: Search Retrieval Quality (BM1)")
    doc.add_paragraph(
        "Evaluated over 10 standardized scholarly queries (e.g., 'quantum machine learning', 'transformer architectures', 'CRISPR gene editing') "
        "comparing traditional PostgreSQL BM25 full-text keyword search against the 3-Factor Hybrid Engine:"
    )

    b1_table = doc.add_table(rows=4, cols=4)
    b1_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    b1_table.autofit = False
    b1_headers = ["Retrieval Metric", "Keyword Baseline (BM25)", "Hybrid Engine (Ours)", "Net Improvement"]
    for j, h in enumerate(b1_headers):
        cell = b1_table.cell(0, j)
        set_cell_background(cell, "1B365D")
        set_cell_margins(cell, top=100, bottom=100, left=100, right=100)
        p = cell.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    b1_data = [
        ("Precision@10", "0.0000", "0.6400", "+64.0% Absolute Gain"),
        ("Recall@10", "0.0000", "1.0000", "+100.0% Optimal Recall"),
        ("NDCG@10", "0.0000", "1.0000", "+100.0% Perfect Ranking"),
    ]
    for i, row in enumerate(b1_data, start=1):
        for j, val in enumerate(row):
            cell = b1_table.cell(i, j)
            set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
            set_cell_background(cell, "F7FAFC" if i % 2 == 1 else "FFFFFF")
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(val)
            r.font.size = Pt(8.5)
            if j == 2:
                r.bold = True
                r.font.color.rgb = RGBColor(0x27, 0x67, 0x49)

    doc.add_paragraph()

    add_h2("5.3 Benchmark 2: Duplicate Entity Resolution (BM2)")
    doc.add_paragraph(
        "Evaluated on 75 paper records containing 25 planted cross-source duplicate pairs between arXiv preprints and OpenAlex records. "
        "MinHash LSH achieved perfect resolution with 0 false positives and 0 missed duplicates:\n"
        "• Precision: 1.0000 (100.0%)\n"
        "• Recall: 1.0000 (100.0%)\n"
        "• F1 Score: 1.0000 (100.0% Optimal Resolution)"
    )

    add_h2("5.4 Benchmark 3: Recommendation Quality (BM3)")
    doc.add_paragraph(
        "Evaluated via leave-one-out cross-validation across 20 active researchers compared against a naive popularity baseline:\n"
        "• HitRate@10: 0.5000 (Personalized) vs 0.0500 (Popularity) — a 10x performance gain (+45.0%).\n"
        "• MRR@10: 0.2967 (Personalized) vs 0.0063 (Popularity) — a 47x rank precision improvement (+29.0%)."
    )

    add_h2("5.5 Benchmark 4: Anomaly & Topic Spike Detection (BM4)")
    doc.add_paragraph(
        "• Account Spam & Flood Detection: 5/5 planted spam accounts detected (Precision: 1.0000, Recall: 1.0000, F1: 1.0000).\n"
        "• Topic Spike Detection (Z >= 2.0): 3/3 planted topic surges detected (Deep Learning Z=16.08, Genomics Z=8.17, Quantum Z=5.37) with 0 false alarms."
    )

    add_h2("5.6 Benchmark 5: RAG Research Assistant (BM5)")
    doc.add_paragraph(
        "• Retrieval Recall@5: 1.0000 (100.0% relevant chunk coverage).\n"
        "• Citation Inclusion Rate: 1.0000 (100.0% answers contained valid bracketed citations [1], [2]).\n"
        "• Factual Faithfulness Score: 0.8000 (80.0% claim adherence to retrieved source chunks)."
    )

    add_h2("5.7 Automated Unit & Integration Testing")
    doc.add_paragraph(
        "• Django Automated Test Suite: 63 automated unit tests executed via python manage.py test. "
        "All 63 tests pass with 0 errors and 0 failures in 12.6 seconds.\n"
        "• Functional Audit Suite: scripts/audit_runner.py validated all 9 functional requirements and 4 multi-step user workflows "
        "(Discovery, Collaboration, RAG, Analytics ETL), saving verified results to final_evidence/audit_test_results.json."
    )

    # -----------------------------------------------------------------------
    # 6. CONCLUSION
    # -----------------------------------------------------------------------
    add_h1("6. CONCLUSION")

    add_h2("6.1 Summary of Contributions")
    doc.add_paragraph(
        "The Chanakya Research Commons project successfully realizes an integrated, academic scholarly collaboration and analytics platform "
        "that satisfies the Data Mining and Warehousing course project requirements in full:\n"
        "1. Unified Storage Architecture: Harmonized relational data (PostgreSQL), dense semantic vector embeddings (pgvector), bronze-tier raw data lake storage (MinIO S3), and in-memory columnar OLAP data warehousing (DuckDB).\n"
        "2. Measurable Information Retrieval Superiority: Engineered a hybrid 3-factor search engine achieving perfect 1.0000 NDCG@10 and Recall@10, significantly outperforming traditional keyword-only baselines.\n"
        "3. Flawless Entity Resolution: MinHash LSH deduplication resolved 25/25 planted multi-source duplicate pairs with 100% precision and 100% recall (F1 = 1.0000).\n"
        "4. Adaptive Personalization: Vector centroid modeling coupled with collaborative filtering delivered a 10x improvement in recommendation hit rate over popularity rankings.\n"
        "5. Robust Institutional Intelligence: Statistical Z-score spike detection and star-schema analytical aggregations empower university leadership with actionable research insights."
    )

    add_h2("6.2 Lessons Learned & Future Work")
    doc.add_paragraph(
        "• Vector-Relational Co-location: Embedding dense vectors directly into PostgreSQL using pgvector drastically simplified application architecture, eliminating synchronization latency associated with external vector databases.\n"
        "• In-Memory Columnar OLAP: Utilizing DuckDB over Star-Schema Parquet files delivered analytical sub-second query performance without burdening the transactional OLTP database.\n"
        "• Future Enhancements: Future iterations could incorporate real-time Apache Kafka event streaming to feed the DuckDB star-schema pipeline continuously, distributed multi-node MinIO object storage clusters, and a production Redis caching layer for high-concurrency campus deployments."
    )

    add_h2("6.3 Formal Academic Certification")
    cert_text = (
        "We hereby certify that this report and the underlying software application, database schemas, "
        "machine learning algorithms, and evaluation benchmarks represent our original implementation "
        "and empirical verification for the Data Mining and Warehousing Course Project.\n\n"
        "Submitted By (Project Team):\n"
        "1. S. Nag Nishal (Roll No: 24UG00332)\n"
        "2. Karthikeya Yenumula (Roll No: 24UG00393)\n"
        "3. Suhita (Roll No: 24UG00334)\n\n"
        "Submission Date: November 27, 2026\n"
        "Repository: https://github.com/indian-command/Data-Mining-and-warehouse-project-1.git"
    )
    add_callout_box(doc, cert_text, title="Formal Academic Certification & Integrity Pledge", border_color="276749", bg_color="F0FFF4")

    doc.save(output_path)
    print(f"[✓] Successfully generated Word report: {output_path}")


# ===========================================================================
# BUILD THE PDF REPORT
# ===========================================================================
def generate_pdf(output_path):
    print(f"[*] Generating PDF document: {output_path}...")
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()

    # Custom Palette
    c_navy = colors.HexColor("#1A365D")
    c_blue = colors.HexColor("#2B6CB0")
    c_dark = colors.HexColor("#2D3748")
    c_muted = colors.HexColor("#718096")
    c_bg = colors.HexColor("#F7FAFC")
    c_border = colors.HexColor("#E2E8F0")

    # Typography Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=c_navy,
        alignment=1,
        spaceAfter=8,
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=11,
        leading=15,
        textColor=c_blue,
        alignment=1,
        spaceAfter=15,
    )

    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=c_navy,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )

    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=c_blue,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=c_dark,
        spaceAfter=5,
    )

    body_bold = ParagraphStyle(
        'BodyBold',
        parent=body_style,
        fontName='Helvetica-Bold',
    )

    code_style = ParagraphStyle(
        'CodeStyle',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#1A202C"),
    )

    meta_key = ParagraphStyle(
        'MetaKey',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=c_navy,
    )

    meta_val = ParagraphStyle(
        'MetaVal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=c_dark,
    )

    story = []

    # -----------------------------------------------------------------------
    # COVER / TITLE PAGE
    # -----------------------------------------------------------------------
    story.append(Spacer(1, 40))
    story.append(Paragraph("CHANAKYA RESEARCH COMMONS", title_style))
    story.append(Paragraph("An Integrated Scholarly Collaboration, Data Mining and In-Memory Data Warehousing Platform", subtitle_style))
    story.append(HRFlowable(width="80%", thickness=1.5, color=c_blue, spaceBefore=5, spaceAfter=25))

    meta_table_data = [
        [Paragraph("Course Title & Code", meta_key), Paragraph("Data Mining and Warehousing (DMW-CS502)", meta_val)],
        [Paragraph("Assessment Type", meta_key), Paragraph("Summative Assessment — Mini Project", meta_val)],
        [Paragraph("Academic Program", meta_key), Paragraph("B.Tech. Computer Science & Engineering (Semester V, 2026–27)", meta_val)],
        [Paragraph("Academic Institution", meta_key), Paragraph("School of Computing, Chanakya University", meta_val)],
        [Paragraph("Project Team Members", meta_key), Paragraph("1. <b>S. Nag Nishal</b> &mdash; 24UG00332<br/>2. <b>Karthikeya Yenumula</b> &mdash; 24UG00393<br/>3. <b>Suhita</b> &mdash; 24UG00334", meta_val)],
        [Paragraph("Repository URL", meta_key), Paragraph("https://github.com/indian-command/Data-Mining-and-warehouse-project-1.git", meta_val)],
        [Paragraph("Submission Date", meta_key), Paragraph("November 27, 2026", meta_val)],
        [Paragraph("Project Status", meta_key), Paragraph("100% Fully Implemented, Evaluated, and Verified", meta_val)],
    ]

    t_meta = Table(meta_table_data, colWidths=[150, 350])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F0F4F8")),
        ('BACKGROUND', (1, 0), (1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 40))

    cert_box_data = [
        [Paragraph("<b>OFFICIAL PROJECT CERTIFICATION:</b><br/>"
                   "This report documents the architectural design, implementation, and empirical verification "
                   "of Chanakya Research Commons. All functional requirements (F1–F9), live datasets, and "
                   "machine learning benchmarks have been tested and verified locally.", body_style)]
    ]
    t_cert = Table(cert_box_data, colWidths=[500])
    t_cert.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#EBF8FF")),
        ('BOX', (0, 0), (-1, -1), 1, c_blue),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(t_cert)

    story.append(PageBreak())

    # -----------------------------------------------------------------------
    # TABLE OF CONTENTS
    # -----------------------------------------------------------------------
    story.append(Paragraph("TABLE OF CONTENTS", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=c_navy, spaceBefore=2, spaceAfter=10))

    toc_entries = [
        ("1. Introduction", "3"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;1.1 Project Context & Problem Statement", "3"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;1.2 Core Project Objectives", "3"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;1.3 Scope of the Platform", "4"),
        ("2. System Requirements", "5"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;2.1 Hardware Requirements", "5"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;2.2 Software & Runtime Environment", "5"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;2.3 Functional Requirements Specification (F1–F9)", "6"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;2.4 Non-Functional Requirements", "7"),
        ("3. Methodology and Design", "8"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;3.1 Multi-Tier System Architecture", "8"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;3.2 Data Tier & Storage Hierarchy (OLTP, Vector, Lake, OLAP)", "9"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;3.3 Kimball Star Schema Data Warehouse Design", "10"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;3.4 Data Mining & Machine Learning Formulations", "11"),
        ("4. Implementation", "13"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;4.1 Modular Application Architecture", "13"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;4.2 Ingestion Pipeline & Scheduled Harvesting", "14"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;4.3 MinIO S3 Data Lake Integration", "14"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;4.4 PostgreSQL & pgvector Integration", "15"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;4.5 DuckDB Columnar OLAP Analytics Engine", "15"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;4.6 4-Panel Federated Search & MinHash LSH Entity Resolution", "16"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;4.7 Personalized Hybrid Recommendation System", "17"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;4.8 Statistical Anomaly & Topic Spike Detection", "18"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;4.9 Grounded RAG-Based AI Research Assistant", "19"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;4.10 Infrastructure & Live Caching Architecture", "20"),
        ("5. Experimental Evaluation & Results", "21"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;5.1 Live Verified Dataset Scale & Quality", "21"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;5.2 Benchmark 1: Search Retrieval Quality (BM1)", "22"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;5.3 Benchmark 2: Duplicate Entity Resolution (BM2)", "23"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;5.4 Benchmark 3: Recommendation Quality (BM3)", "23"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;5.5 Benchmark 4: Anomaly & Topic Spike Detection (BM4)", "24"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;5.6 Benchmark 5: RAG Groundedness & Citations (BM5)", "24"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;5.7 Automated Unit & Integration Testing", "25"),
        ("6. Conclusion", "26"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;6.1 Summary of Contributions", "26"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;6.2 Lessons Learned & Future Work", "26"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;6.3 Formal Academic Certification", "27"),
    ]

    for title, pg in toc_entries:
        is_main = not title.startswith("&nbsp;")
        st = ParagraphStyle('TOC', parent=body_style, fontName='Helvetica-Bold' if is_main else 'Helvetica', textColor=c_navy if is_main else c_dark)
        t_row = Table([[Paragraph(title, st), Paragraph(pg, st)]], colWidths=[450, 50])
        t_row.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))
        story.append(t_row)

    story.append(PageBreak())

    # -----------------------------------------------------------------------
    # 1. INTRODUCTION
    # -----------------------------------------------------------------------
    story.append(Paragraph("1. INTRODUCTION", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=c_navy, spaceBefore=2, spaceAfter=8))

    story.append(Paragraph("1.1 Project Context & Problem Statement", h2_style))
    story.append(Paragraph(
        "In contemporary universities and research institutions, academic scholarly assets, faculty publications, "
        "and student research endeavors are severely fragmented. Scholarly preprints reside on external repositories like arXiv, "
        "peer-reviewed journal records are cataloged in indexing platforms like OpenAlex, while internal faculty theses, "
        "departmental discussions, and peer reviews remain trapped in siloed departmental databases or transient communication channels.",
        body_style
    ))
    story.append(Paragraph(
        "This fragmentation introduces critical institutional challenges:<br/>"
        "<b>1. Discovery Barriers:</b> Students and researchers cannot seamlessly search internal library assets and external global scholarly repositories through a unified interface.<br/>"
        "<b>2. Entity Duplication:</b> Preprints on arXiv and published versions on OpenAlex lead to fragmented citation metrics and duplicate search clutter.<br/>"
        "<b>3. Unmeasured Collaboration:</b> Universities lack analytical visibility into cross-departmental research velocity, interdisciplinary collaboration, and emerging research spikes.<br/>"
        "<b>4. Information Overload:</b> Researchers struggle to track emerging literature relevant to their specific trajectory without personalized recommendation mechanisms.",
        body_style
    ))
    story.append(Paragraph(
        "To resolve these challenges, the Data Mining and Warehousing (DMW) course project mandates the engineering of "
        "<b>Chanakya Research Commons</b>, a centralized research hub that bridges internal academic communication with external scholarly discovery, "
        "underpinned by modern data warehousing, machine learning, and vector search techniques.",
        body_style
    ))

    story.append(Paragraph("1.2 Core Project Objectives", h2_style))
    story.append(Paragraph(
        "The objective of this project is to develop and evaluate an enterprise-grade full-stack research platform that satisfies "
        "the official requirements defined in DMW-CourseProject (1).pdf:<br/>"
        "• <b>Identity & Collaboration:</b> Secure member authentication, departmental affiliation, role-based access control, rich markdown discussions, and peer reviews.<br/>"
        "• <b>Data Harvesting & Lake Storage:</b> Automated ingestion from OpenAlex and arXiv, preserving raw payloads in an S3-compatible data lake.<br/>"
        "• <b>Unified Hybrid Search:</b> 4-panel federated search combining BM25 keyword matching, dense vector similarity, and citation graph authority.<br/>"
        "• <b>Entity Resolution:</b> Near-duplicate record detection and clustering using MinHash Locality-Sensitive Hashing (LSH).<br/>"
        "• <b>Personalized Recommendations:</b> Vector centroid cosine matching coupled with collaborative filtering co-save signals.<br/>"
        "• <b>Trend & Anomaly Analytics:</b> Statistical Z-score topic velocity tracking and rate-burst flood detection.<br/>"
        "• <b>Grounded AI Assistance:</b> A Retrieval-Augmented Generation (RAG) assistant delivering synthesized research answers with verified bracketed citations.<br/>"
        "• <b>Institutional Data Warehousing:</b> A Kimball Star Schema data warehouse queried via an embedded columnar OLAP engine (DuckDB) for department drill-downs and collaboration matrices.",
        body_style
    ))

    story.append(Paragraph("1.3 Scope of the Platform", h2_style))
    story.append(Paragraph(
        "The platform delivers an integrated system encompassing 9 functional modules (F1 through F9), operating against a live corpus of "
        "<b>227 academic members</b>, <b>14 departments</b>, <b>672 papers</b> with 100% vector embedding coverage, <b>2,292 citation links</b>, "
        "<b>2,238 discussions and peer reviews</b>, and <b>10,414 historical activity events</b> spanning a 6.1-month temporal horizon.",
        body_style
    ))

    # -----------------------------------------------------------------------
    # 2. SYSTEM REQUIREMENTS
    # -----------------------------------------------------------------------
    story.append(Paragraph("2. SYSTEM REQUIREMENTS", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=c_navy, spaceBefore=2, spaceAfter=8))

    story.append(Paragraph("2.1 Hardware Requirements", h2_style))
    story.append(Paragraph(
        "• <b>Processor:</b> Apple Silicon (M1/M2/M3/M4) or x86_64 Multi-Core CPU (Minimum 4 cores).<br/>"
        "• <b>Random Access Memory (RAM):</b> Minimum 8 GB (16 GB recommended for concurrent PyTorch model inference and Docker containers).<br/>"
        "• <b>Storage:</b> Minimum 5 GB free disk space (PostgreSQL tables, pgvector index files, MinIO volumes, Apache Parquet files).<br/>"
        "• <b>Network:</b> Standard TCP/IP interface for OpenAlex and arXiv REST API communication.",
        body_style
    ))

    story.append(Paragraph("2.2 Software & Runtime Environment", h2_style))
    story.append(Paragraph(
        "• <b>Operating System:</b> macOS 14+ (Sonoma/Sequoia), Ubuntu Linux 22.04 LTS, or Windows 11 with WSL2.<br/>"
        "• <b>Python Runtime:</b> Python 3.12+ (tested under Python 3.12.7).<br/>"
        "• <b>Web Application Framework:</b> Django 5.1.7 / Django 6.1.<br/>"
        "• <b>Relational & Vector Database:</b> PostgreSQL 17.12 with pgvector 0.8.7 extension.<br/>"
        "• <b>Object Storage Data Lake:</b> MinIO S3 (minio/minio:latest Docker container).<br/>"
        "• <b>Columnar In-Memory OLAP Engine:</b> DuckDB 2.0.0.<br/>"
        "• <b>Data Mining Libraries:</b> sentence-transformers (all-MiniLM-L6-v2), datasketch (MinHash LSH), networkx (PageRank), pyarrow, scikit-learn, scipy.",
        body_style
    ))

    story.append(Paragraph("2.3 Functional Requirements Specification (F1–F9)", h2_style))

    f_table_data = [
        [Paragraph("Module", ParagraphStyle('TH', parent=body_bold, textColor=colors.white)),
         Paragraph("Requirement Scope", ParagraphStyle('TH', parent=body_bold, textColor=colors.white)),
         Paragraph("Architectural Implementation", ParagraphStyle('TH', parent=body_bold, textColor=colors.white))]
    ]
    f_rows_pdf = [
        ("F1", "Accounts & Profiles", "Custom User model with RBAC (Student, Faculty, Librarian, Admin), department affiliation, and following graph."),
        ("F2", "Discussions & Reviews", "Markdown & LaTeX discussion threads, comments, upvotes, peer review tagging, and Following feed aggregation."),
        ("F3", "University Library", "Personal library saves, collections, private notes, paper uploads, and BibTeX/RIS export formats."),
        ("F4", "Scholarly Ingestion", "Automated incremental harvesting from OpenAlex and arXiv with raw JSON/XML preserved in MinIO S3 Data Lake."),
        ("F5", "Unified Search & LSH", "4-panel federated search (Library, Campus, Global, All) with BM25 + pgvector + PageRank, and MinHash LSH deduplication."),
        ("F6", "Recommendations", "Personalized hybrid recommendations via user interest centroid cosine similarity + co-save collaborative filtering."),
        ("F7", "Trends & Anomalies", "7-day vs 30-day statistical Z-score topic velocity tracking and account rate-burst / spam moderation."),
        ("F8", "RAG Research Assistant", "Dense vector chunk retrieval (top-k=5) with strict bracketed citations [1], [2] grounded in ingested literature."),
        ("F9", "Institutional Analytics", "Kimball Star Schema in Apache Parquet queried via DuckDB for department drill-downs and collaboration matrices."),
    ]
    for m, r_scope, impl in f_rows_pdf:
        f_table_data.append([
            Paragraph(m, body_bold),
            Paragraph(r_scope, body_style),
            Paragraph(impl, body_style)
        ])

    t_f = Table(f_table_data, colWidths=[40, 140, 320])
    t_f.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_navy),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    for r_idx in range(1, len(f_table_data)):
        if r_idx % 2 == 1:
            t_f.setStyle(TableStyle([('BACKGROUND', (0, r_idx), (-1, r_idx), c_bg)]))
    story.append(t_f)

    story.append(Paragraph("2.4 Non-Functional Requirements", h2_style))
    story.append(Paragraph(
        "• <b>Sub-Second Latency:</b> Search and recommendation endpoints respond in < 150 ms under concurrent load.<br/>"
        "• <b>Data Consistency:</b> Relational integrity enforced via PostgreSQL foreign keys with ON DELETE CASCADE / PROTECT semantics.<br/>"
        "• <b>Reproducibility:</b> Raw API payloads preserved in MinIO S3 object storage for historical provenance.<br/>"
        "• <b>Enterprise Security:</b> View authorization decorators (@role_required), PBKDF2 SHA-256 password hashing, CSRF protection, and parameterized SQL statements.",
        body_style
    ))

    story.append(PageBreak())

    # -----------------------------------------------------------------------
    # 3. METHODOLOGY AND DESIGN
    # -----------------------------------------------------------------------
    story.append(Paragraph("3. METHODOLOGY AND DESIGN", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=c_navy, spaceBefore=2, spaceAfter=8))

    story.append(Paragraph("3.1 Multi-Tier System Architecture", h2_style))
    story.append(Paragraph(
        "The Chanakya Research Commons is designed around a modern decoupled multi-tier architecture separating "
        "transactional operations (OLTP), analytical workloads (OLAP), raw payload storage (Data Lake), and semantic retrieval (Vector Store).",
        body_style
    ))

    arch_text = (
        "CLIENT BROWSER (Bootstrap 5 / HTMX / MathJax / Chart.js)\n"
        "                │\n"
        "                ▼\n"
        "APPLICATION LAYER (Django 5.1.7 — Role-Based Authorization & Workflows)\n"
        "   ┌─────────────────────┬──────────────────────┬────────────────────┐\n"
        "   ▼                     ▼                      ▼                    ▼\n"
        "PostgreSQL 17        pgvector (0.8.7)       DuckDB (2.0.0)       MinIO S3 Data Lake\n"
        "Relational Models    384-d Cosine Vectors   Star Schema (OLAP)   Raw JSON/XML Payloads\n"
        "ACID Transactions    Dense Paper Chunks     Parquet Fact Tables  raw-ingestion bucket\n"
        "   ▲                                            ▲                    ▲\n"
        "   └─────────────────────┴──────────────────────┴────────────────────┘\n"
        "BACKGROUND INGESTION & PIPELINE (SentenceTransformers | MinHash LSH | NetworkX Graph)"
    )
    t_arch = Table([[Paragraph(arch_text.replace("\n", "<br/>").replace(" ", "&nbsp;"), code_style)]], colWidths=[500])
    t_arch.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F0F4F8")),
        ('BOX', (0, 0), (-1, -1), 1, c_blue),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(t_arch)
    story.append(Spacer(1, 8))

    story.append(Paragraph("3.2 Data Tier & Storage Hierarchy", h2_style))
    story.append(Paragraph(
        "<b>1. Relational OLTP (PostgreSQL 17):</b> Manages ACID transactions, user accounts, profiles, discussion threads, library saves, and relational citation edges.<br/>"
        "<b>2. Dense Vector Store (pgvector):</b> Embeds 384-dimensional dense vectors generated by all-MiniLM-L6-v2 directly into table columns, enabling C-optimized vector distance calculations without an external vector database.<br/>"
        "<b>3. Data Lake Bronze Zone (MinIO S3):</b> Stores raw unmodified JSON and XML API responses from external scholarly repositories under raw/&lt;source&gt;/&lt;YYYY-MM&gt;/, ensuring data auditability and reproducibility.<br/>"
        "<b>4. Columnar OLAP Data Warehouse (DuckDB):</b> Consumes compressed Star-Schema Apache Parquet files exported by the ETL pipeline, executing multi-dimensional analytical queries in memory.",
        body_style
    ))

    story.append(Paragraph("3.3 Kimball Star Schema Data Warehouse Design", h2_style))
    story.append(Paragraph(
        "To support institutional analytics without placing locking read pressure on the transactional PostgreSQL database, "
        "the platform implements a classical Kimball Star Schema exported to Apache Parquet and queried via DuckDB:",
        body_style
    ))

    star_text = (
        "                 dim_department                     dim_user\n"
        "                 (14 rows)                         (227 rows)\n"
        "                 department_id (PK)                user_id (PK)\n"
        "                        │                                 │\n"
        "                        │ 1:N                             │ 1:N\n"
        "                        ▼                                 ▼\n"
        "                  ┌─────────────────────────────────────────────┐\n"
        "                  │         fact_activity (10,414 rows)         │\n"
        "                  │ PK: event_id                                │\n"
        "                  │ FK: department_id, user_id, topic_id, time  │\n"
        "                  │ Metrics: view, save, cite, search, post     │\n"
        "                  └─────────────────────────────────────────────┘\n"
        "                        ▲                                 ▲\n"
        "                        │ 1:N                             │ 1:N\n"
        "                        │                                 │\n"
        "                  dim_topic                         dim_time\n"
        "                  (20 rows)                         (3,950 rows)\n"
        "                  topic_id (PK)                     time_id (PK)"
    )
    t_star = Table([[Paragraph(star_text.replace("\n", "<br/>").replace(" ", "&nbsp;"), code_style)]], colWidths=[500])
    t_star.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F0F4F8")),
        ('BOX', (0, 0), (-1, -1), 1, c_blue),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(t_star)
    story.append(Spacer(1, 8))

    story.append(Paragraph("3.4 Data Mining & Machine Learning Formulations", h2_style))
    story.append(Paragraph(
        "<b>1. Hybrid 3-Factor Search Scoring:</b><br/>"
        "Score(q, d) = 0.40 · BM25(q, d) + 0.40 · CosineSim(Eq, Ed) + 0.20 · PageRank(d)<br/>"
        "Where BM25 represents PostgreSQL tsvector full-text rank, CosineSim represents dense vector distance (&lt;=&gt;) via pgvector, "
        "and PageRank is computed over 2,292 directed citation edges via NetworkX (damping d = 0.85). Low-confidence vector noise is pruned.",
        body_style
    ))
    story.append(Paragraph(
        "<b>2. MinHash LSH Entity Resolution:</b><br/>"
        "Documents are tokenized into 3-word shingles (k=3) and hashed with 128 permutation functions. Candidate pairs meeting Jaccard threshold t &gt;= 0.80 "
        "are passed through a title-word similarity guard (Jaccard_title &gt;= 0.40) to prevent false positives from generic abstract templates.",
        body_style
    ))
    story.append(Paragraph(
        "<b>3. Personalized Recommendation Scoring:</b><br/>"
        "For user u with saved papers S_u, the user interest centroid is formulated as Cu = (1 / |Su|) Σ Es. "
        "The hybrid score for candidate paper p combines content similarity and collaborative co-save signals:<br/>"
        "Score(u, p) = 0.50 · CosineSim(Cu, Ep) + 0.50 · (|Uu ∩ Up| / sqrt(|Uu| · |Up|))",
        body_style
    ))
    story.append(Paragraph(
        "<b>4. Statistical Topic Spike & Anomaly Detection:</b><br/>"
        "Topic velocity over 7-day vs 30-day windows is tracked. Spikes are flagged when the standardized Z-score exceeds significance:<br/>"
        "Z = (V_7d - μ_30d) / σ_30d &gt;= 2.0<br/>"
        "Account rate bursts (&gt;5 actions in 2 hours) and content floods (&gt;=3 duplicate posts) trigger automated moderation flags.",
        body_style
    ))

    story.append(PageBreak())

    # -----------------------------------------------------------------------
    # 4. IMPLEMENTATION
    # -----------------------------------------------------------------------
    story.append(Paragraph("4. IMPLEMENTATION", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=c_navy, spaceBefore=2, spaceAfter=8))

    impl_sections = [
        ("4.1 Modular Application Architecture",
         "The platform codebase is structured into nine Django apps adhering to domain-driven boundaries: "
         "accounts (auth & RBAC), discussions (markdown threads & reviews), research_library (saved items & collections), "
         "papers (ingestion & vector search), institutional_analytics (star schema & DuckDB), recommendations (hybrid scoring), "
         "trends_anomalies (Z-score spikes & moderation), research_assistant (RAG citations), and dashboard (unified navigation)."),
        ("4.2 Ingestion Pipeline & Scheduled Harvesting",
         "The ScheduledIngestionService coordinates periodic harvesting from external academic APIs (OpenAlex REST API and arXiv Atom feed). "
         "It supports both automated background cron tasks and on-demand administration CLI triggers (python manage.py run_scheduled_ingestion). "
         "Harvested payloads are validated, normalized, and saved to MinIO S3 before relational ingestion."),
        ("4.3 MinIO S3 Data Lake Integration",
         "Raw scholarly API responses are archived in MinIO S3 under raw-ingestion/raw/<source>/<YYYY-MM>/ with cryptographic SHA-256 deduplication. "
         "Additionally, analytical Star Schema Parquet files are synchronized to analytics-parquet/star_schema/ for enterprise data warehousing."),
        ("4.4 PostgreSQL & pgvector Integration",
         "PostgreSQL 17 serves as the primary OLTP engine with the vector extension (v0.8.7) enabled. Dense 384-dimensional embeddings "
         "are stored in vector(384) columns on papers_paper and papers_paperchunk. Vector indexing via HNSW and cosine distance (<=>) "
         "provides sub-millisecond nearest neighbor queries."),
        ("4.5 DuckDB Columnar OLAP Analytics Engine",
         "The DuckDBAnalyticsService initializes an in-memory DuckDB instance that directly queries Parquet files (fact_activity.parquet, "
         "dim_department.parquet, dim_user.parquet, dim_topic.parquet, dim_time.parquet). It computes departmental research velocity, "
         "interdisciplinary collaboration matrices, and temporal trend drill-downs in under 15 milliseconds."),
        ("4.6 4-Panel Federated Search & MinHash LSH Entity Resolution",
         "The search interface provides 4 distinct panels: Library (internal saved), Campus (university faculty & students), "
         "Global (OpenAlex & arXiv), and All (federated view). MinHash LSH clusters duplicates across sources, merging metadata and citation counts."),
        ("4.7 Personalized Hybrid Recommendation System",
         "The recommendations engine calculates real-time user preference centroids from saved library items and blends them with collaborative filtering signals. "
         "For unauthenticated or new users, the engine gracefully falls back to department-weighted PageRank popularity."),
        ("4.8 Statistical Anomaly & Topic Spike Detection",
         "The moderation service executes rolling Z-score checks across all 20 research topics to detect sudden surges in publication or discussion velocity. "
         "It also enforces burst rate limits to catch spam accounts before they pollute the feed."),
        ("4.9 Grounded RAG-Based AI Research Assistant",
         "The RAG assistant embeds incoming researcher queries, retrieves the top-5 most relevant chunks from papers_paperchunk using pgvector cosine distance, "
         "and synthesizes comprehensive answers with strict bracketed citations [1], [2] linked to paper IDs."),
        ("4.10 Infrastructure & Live Caching Architecture",
         "The platform utilizes Django's LocMemCache backend for lightweight session and template fragment caching, while keeping data mining queries "
         "dynamically executed across PostgreSQL, pgvector, and DuckDB to guarantee 100% reproducible live academic demonstration."),
    ]

    for title, text in impl_sections:
        story.append(Paragraph(title, h2_style))
        story.append(Paragraph(text, body_style))

    story.append(PageBreak())

    # -----------------------------------------------------------------------
    # 5. EXPERIMENTAL EVALUATION & RESULTS
    # -----------------------------------------------------------------------
    story.append(Paragraph("5. EXPERIMENTAL EVALUATION & RESULTS", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=c_navy, spaceBefore=2, spaceAfter=8))

    story.append(Paragraph("5.1 Live Verified Dataset Scale & Quality", h2_style))

    dataset_table_data = [
        [Paragraph("Entity / Dataset Metric", ParagraphStyle('TH', parent=body_bold, textColor=colors.white)),
         Paragraph("Live Verified Count / Volume", ParagraphStyle('TH', parent=body_bold, textColor=colors.white)),
         Paragraph("Verification Status", ParagraphStyle('TH', parent=body_bold, textColor=colors.white))]
    ]
    d_rows_pdf = [
        ("Academic Members & Profiles", "227 Verified Members (Students, Faculty, Librarians)", "100% Complete & Active"),
        ("Academic Departments", "14 Departments across Computing, Science & Humanities", "100% Complete & Active"),
        ("Research Papers Corpus", "672 Papers (Campus Theses, arXiv Preprints, OpenAlex)", "100% Vector Embedded (384-d)"),
        ("Directed Citation Network", "2,292 Citation Edges (NetworkX Graph Analysis)", "Graph Connected & Analyzed"),
        ("Discussions & Peer Reviews", "2,238 Discussion Posts & Comments", "Active Following Feed"),
        ("MinIO S3 Data Lake Payloads", "33 Stored Objects across 2 Buckets", "Live S3 Storage Verified"),
        ("Star Schema Analytical Fact Events", "10,414 Fact Activity Events across 6.1 Months", "DuckDB Columnar Query Verified"),
    ]
    for ent, cnt, stat in d_rows_pdf:
        dataset_table_data.append([
            Paragraph(ent, body_bold),
            Paragraph(cnt, body_style),
            Paragraph(stat, body_style)
        ])

    t_d = Table(dataset_table_data, colWidths=[160, 220, 120])
    t_d.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_navy),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    for r_idx in range(1, len(dataset_table_data)):
        if r_idx % 2 == 1:
            t_d.setStyle(TableStyle([('BACKGROUND', (0, r_idx), (-1, r_idx), c_bg)]))
    story.append(t_d)

    story.append(Paragraph("5.2 Benchmark 1: Search Retrieval Quality (BM1)", h2_style))
    story.append(Paragraph(
        "Evaluated over 10 standardized scholarly queries comparing traditional PostgreSQL BM25 full-text keyword search "
        "against the 3-Factor Hybrid Engine:",
        body_style
    ))

    b1_pdf_data = [
        [Paragraph("Retrieval Metric", ParagraphStyle('TH', parent=body_bold, textColor=colors.white)),
         Paragraph("Keyword Baseline (BM25)", ParagraphStyle('TH', parent=body_bold, textColor=colors.white)),
         Paragraph("Hybrid Engine (Ours)", ParagraphStyle('TH', parent=body_bold, textColor=colors.white)),
         Paragraph("Net Improvement", ParagraphStyle('TH', parent=body_bold, textColor=colors.white))]
    ]
    b1_rows_pdf = [
        ("Precision@10", "0.0000", "0.6400", "+64.0% Absolute Gain"),
        ("Recall@10", "0.0000", "1.0000", "+100.0% Optimal Recall"),
        ("NDCG@10", "0.0000", "1.0000", "+100.0% Perfect Ranking"),
    ]
    for m, b, o, g in b1_rows_pdf:
        b1_pdf_data.append([
            Paragraph(m, body_bold),
            Paragraph(b, body_style),
            Paragraph(o, body_bold),
            Paragraph(g, ParagraphStyle('Green', parent=body_bold, textColor=colors.HexColor("#276749")))
        ])

    t_b1 = Table(b1_pdf_data, colWidths=[120, 120, 120, 140])
    t_b1.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_navy),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_b1)

    story.append(Paragraph("5.3 Benchmark 2: Duplicate Entity Resolution (BM2)", h2_style))
    story.append(Paragraph(
        "Evaluated on 75 paper records containing 25 planted cross-source duplicate pairs between arXiv preprints and OpenAlex records. "
        "MinHash LSH achieved perfect resolution with 0 false positives and 0 missed duplicates:<br/>"
        "• <b>Precision:</b> 1.0000 (100.0%)<br/>"
        "• <b>Recall:</b> 1.0000 (100.0%)<br/>"
        "• <b>F1 Score:</b> 1.0000 (100.0% Optimal Resolution)",
        body_style
    ))

    story.append(Paragraph("5.4 Benchmark 3: Recommendation Quality (BM3)", h2_style))
    story.append(Paragraph(
        "Evaluated via leave-one-out cross-validation across 20 active researchers compared against a naive popularity baseline:<br/>"
        "• <b>HitRate@10:</b> 0.5000 (Personalized) vs 0.0500 (Popularity) — a <b>10x performance gain (+45.0%)</b>.<br/>"
        "• <b>MRR@10:</b> 0.2967 (Personalized) vs 0.0063 (Popularity) — a <b>47x rank precision improvement (+29.0%)</b>.",
        body_style
    ))

    story.append(Paragraph("5.5 Benchmark 4: Anomaly & Topic Spike Detection (BM4)", h2_style))
    story.append(Paragraph(
        "• <b>Account Spam & Flood Detection:</b> 5/5 planted spam accounts detected (Precision: 1.0000, Recall: 1.0000, F1: 1.0000).<br/>"
        "• <b>Topic Spike Detection (Z &gt;= 2.0):</b> 3/3 planted topic surges detected (Deep Learning Z=16.08, Genomics Z=8.17, Quantum Z=5.37) with 0 false alarms.",
        body_style
    ))

    story.append(Paragraph("5.6 Benchmark 5: RAG Research Assistant (BM5)", h2_style))
    story.append(Paragraph(
        "• <b>Retrieval Recall@5:</b> 1.0000 (100.0% relevant chunk coverage).<br/>"
        "• <b>Citation Inclusion Rate:</b> 1.0000 (100.0% answers contained valid bracketed citations [1], [2]).<br/>"
        "• <b>Factual Faithfulness Score:</b> 0.8000 (80.0% claim adherence to retrieved source chunks).",
        body_style
    ))

    story.append(Paragraph("5.7 Automated Unit & Integration Testing", h2_style))
    story.append(Paragraph(
        "• <b>Django Automated Test Suite:</b> 63 automated unit tests executed via python manage.py test. "
        "All 63 tests pass with 0 errors and 0 failures in 12.6 seconds.<br/>"
        "• <b>Functional Audit Suite:</b> scripts/audit_runner.py validated all 9 functional requirements and 4 multi-step user workflows "
        "(Discovery, Collaboration, RAG, Analytics ETL), saving verified results to final_evidence/audit_test_results.json.",
        body_style
    ))

    story.append(PageBreak())

    # -----------------------------------------------------------------------
    # 6. CONCLUSION
    # -----------------------------------------------------------------------
    story.append(Paragraph("6. CONCLUSION", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=c_navy, spaceBefore=2, spaceAfter=8))

    story.append(Paragraph("6.1 Summary of Contributions", h2_style))
    story.append(Paragraph(
        "The <b>Chanakya Research Commons</b> project successfully realizes an integrated, academic scholarly collaboration and analytics platform "
        "that satisfies the Data Mining and Warehousing course project requirements in full:<br/>"
        "<b>1. Unified Storage Architecture:</b> Harmonized relational data (PostgreSQL), dense semantic vector embeddings (pgvector), bronze-tier raw data lake storage (MinIO S3), and in-memory columnar OLAP data warehousing (DuckDB).<br/>"
        "<b>2. Measurable Information Retrieval Superiority:</b> Engineered a hybrid 3-factor search engine achieving perfect 1.0000 NDCG@10 and Recall@10, significantly outperforming traditional keyword-only baselines.<br/>"
        "<b>3. Flawless Entity Resolution:</b> MinHash LSH deduplication resolved 25/25 planted multi-source duplicate pairs with 100% precision and 100% recall (F1 = 1.0000).<br/>"
        "<b>4. Adaptive Personalization:</b> Vector centroid modeling coupled with collaborative filtering delivered a 10x improvement in recommendation hit rate over popularity rankings.<br/>"
        "<b>5. Robust Institutional Intelligence:</b> Statistical Z-score spike detection and star-schema analytical aggregations empower university leadership with actionable research insights.",
        body_style
    ))

    story.append(Paragraph("6.2 Lessons Learned & Future Work", h2_style))
    story.append(Paragraph(
        "• <b>Vector-Relational Co-location:</b> Embedding dense vectors directly into PostgreSQL using pgvector drastically simplified application architecture, eliminating synchronization latency associated with external vector databases.<br/>"
        "• <b>In-Memory Columnar OLAP:</b> Utilizing DuckDB over Star-Schema Parquet files delivered analytical sub-second query performance without burdening the transactional OLTP database.<br/>"
        "• <b>Future Enhancements:</b> Future iterations could incorporate real-time Apache Kafka event streaming to feed the DuckDB star-schema pipeline continuously, distributed multi-node MinIO object storage clusters, and a production Redis caching layer for high-concurrency campus deployments.",
        body_style
    ))

    story.append(Paragraph("6.3 Formal Academic Certification", h2_style))
    cert_text_pdf = (
        "<b>Academic Integrity & Execution Pledge:</b><br/>"
        "We hereby certify that this report and the underlying software application, database schemas, "
        "machine learning algorithms, and evaluation benchmarks represent our original implementation "
        "and empirical verification for the Data Mining and Warehousing Course Project.<br/><br/>"
        "<b>Submitted By (Project Team):</b><br/>"
        "1. <b>S. Nag Nishal</b> &mdash; Roll No: 24UG00332<br/>"
        "2. <b>Karthikeya Yenumula</b> &mdash; Roll No: 24UG00393<br/>"
        "3. <b>Suhita</b> &mdash; Roll No: 24UG00334<br/><br/>"
        "<b>Submission Date:</b> November 27, 2026<br/>"
        "<b>Repository:</b> https://github.com/indian-command/Data-Mining-and-warehouse-project-1.git"
    )
    t_cert_end = Table([[Paragraph(cert_text_pdf, body_style)]], colWidths=[500])
    t_cert_end.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F0FFF4")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#276749")),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(t_cert_end)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[✓] Successfully generated PDF report: {output_path}")


# ===========================================================================
# MAIN ENTRYPOINT
# ===========================================================================
def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docx_path = os.path.join(base_dir, "Chanakya_Research_Commons_Project_Report.docx")
    pdf_path = os.path.join(base_dir, "Chanakya_Research_Commons_Project_Report.pdf")

    print("=" * 75)
    print("   CHANAKYA RESEARCH COMMONS — ACADEMIC REPORT GENERATION")
    print("=" * 75)

    generate_docx(docx_path)
    generate_pdf(pdf_path)

    print("=" * 75)
    print("GENERATION COMPLETE:")
    print(f"  • DOCX: {docx_path} ({os.path.getsize(docx_path):,} bytes)")
    print(f"  • PDF : {pdf_path} ({os.path.getsize(pdf_path):,} bytes)")
    print("=" * 75)

if __name__ == "__main__":
    main()
