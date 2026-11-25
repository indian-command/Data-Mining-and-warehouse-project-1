import os
import sys
import json
import re
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction
from accounts.models import School, Department, Topic, Profile, MemberFollow, TopicFollow
from papers.models import Paper

User = get_user_model()

def seed_real_chanakya_data():
    print("=" * 70)
    print("SEEDING REAL CHANAKYA UNIVERSITY DATA FROM OFFICIAL PORTAL")
    print("=" * 70)

    # 1. 6 OFFICIAL SCHOOLS
    official_schools = [
        ("School of Biosciences", "SBS", "Pioneering research in molecular biology, genomics, structural biology, and translational healthcare."),
        ("School of Engineering", "SOE", "Advancing artificial intelligence, computational systems, robotics, and cutting-edge engineering disciplines."),
        ("School of Arts, Humanities and Social Sciences", "SAHSS", "Deep engagement with society, culture, cognitive psychology, and Indian Knowledge Systems."),
        ("School of Management Sciences", "SMS", "Interdisciplinary business leadership, financial analytics, public enterprise, and institutional governance."),
        ("School of Mathematics and Natural Sciences", "SMNS", "Fundamental inquiry into discrete algorithms, theoretical physics, and computational mathematics."),
        ("School of Law, Governance and Public Policy", "SLGPP", "Excellence in legal jurisprudence, constitutional studies, and evidence-based public policymaking."),
    ]

    school_map = {}
    for name, code, desc in official_schools:
        s, created = School.objects.update_or_create(
            code=code,
            defaults={"name": name, "description": desc}
        )
        school_map[code] = s
        print(f"School: [{code}] {name} ({'created' if created else 'updated'})")

    # 2. OFFICIAL DEPARTMENTS
    official_departments = [
        ("Department of Biosciences & Biotechnology", "DBIO", "SBS", "Molecular genomics, structural biology, and computational bioinformatics."),
        ("Department of Computer Science & Engineering", "DCSE", "SOE", "AI systems, machine learning, distributed computing, and cybersecurity."),
        ("Department of Psychology & Cognitive Sciences", "DPC", "SAHSS", "Behavioral neuroscience, clinical psychology, and cognitive development."),
        ("Department of Indian Knowledge Systems", "DIKS", "SAHSS", "Traditional Indian sciences, Sanskrit epistemology, and heritage technologies."),
        ("Department of Management Studies & Analytics", "DMS", "SMS", "Strategic management, business intelligence, and financial modeling."),
        ("Department of Mathematics & Computing", "DMC", "SMNS", "Optimization algorithms, discrete mathematics, and statistical learning."),
        ("Department of Law & Jurisprudence", "DLAW", "SLGPP", "Constitutional law, regulatory frameworks, and intellectual property."),
        ("Department of Public Policy & Governance", "DPPG", "SLGPP", "Institutional governance, policy evaluation, and sustainability frameworks."),
    ]

    dept_map = {}
    for name, code, scode, desc in official_departments:
        d, created = Department.objects.update_or_create(
            code=code,
            defaults={"name": name, "school": school_map[scode], "description": desc}
        )
        dept_map[code] = d
        print(f"  Dept: [{code}] {name} -> {scode}")

    # 3. RESEARCH TOPICS
    official_topics = [
        ("Indian Knowledge Systems (IKS)", "Vedic epistemology, Sanskrit heritage, and traditional sciences."),
        ("Biosciences & Genomics", "CRISPR, molecular genetics, and structural biology."),
        ("Artificial Intelligence & NLP", "Transformers, LLMs, reinforcement learning, and computer vision."),
        ("Public Policy & Governance", "Evidence-based policymaking, civic tech, and regulatory governance."),
        ("Management & Financial Analytics", "Econometrics, corporate strategy, and quantitative finance."),
        ("Computational Mathematics", "Numerical analysis, cryptography, and graph algorithms."),
        ("Cognitive Psychology", "Behavioral experiments, mental health, and cognitive modeling."),
        ("Sustainable Development & Clean Energy", "Renewable energy, climate modeling, and ESG frameworks."),
    ]

    topic_objs = []
    for name, desc in official_topics:
        t, _ = Topic.objects.update_or_create(name=name, defaults={"description": desc})
        topic_objs.append(t)

    # 4. LOAD SCRAPED REAL PROFESSORS
    json_path = "/Users/nagnishal/.gemini/antigravity/brain/515e5a5b-764f-4ed6-8fc4-847f8160772a/scratch/chanakya_real_faculty.json"
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found")
        return

    with open(json_path) as f:
        faculty_raw = json.load(f)

    print(f"\nProcessing {len(faculty_raw)} scraped faculty records...")

    # Map school name keywords to Department code
    def find_department(text):
        t = text.lower()
        if "bio" in t or "science" in t and "bioscience" in t:
            return dept_map["DBIO"]
        elif "engineer" in t or "comput" in t or "tech" in t:
            return dept_map["DCSE"]
        elif "iks" in t or "sanskrit" in t:
            return dept_map["DIKS"]
        elif "psych" in t or "humanit" in t or "social" in t:
            return dept_map["DPC"]
        elif "manage" in t or "commerce" in t or "business" in t:
            return dept_map["DMS"]
        elif "math" in t or "natural" in t:
            return dept_map["DMC"]
        elif "law" in t or "policy" in t or "governance" in t:
            return dept_map["DLAW"]
        return dept_map["DMS"]  # default fallback

    # Top faculty to ensure created with high fidelity
    created_count = 0
    seen_users = set()

    for idx, item in enumerate(faculty_raw):
        name = item.get("name", "").strip()
        if not name or len(name) < 4:
            continue

        # Clean name parts
        clean_name = re.sub(r'^(Dr\.?|Prof\.?|Mr\.?|Ms\.?|Mrs\.?)\s+', '', name, flags=re.I).strip()
        parts = clean_name.split()
        first_name = parts[0]
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        # Make username
        username_base = f"{first_name.lower()}{last_name[:3].lower()}".replace(" ", "").replace(".", "")
        username = re.sub(r'[^a-z0-9]', '', username_base)
        if not username:
            username = f"faculty_{idx}"

        if username in seen_users:
            username = f"{username}_{idx}"
        seen_users.add(username)

        # Department
        dept = find_department(item.get("designation", "") + " " + item.get("extra", ""))

        # Bio
        bio_lines = []
        if item.get("designation"):
            bio_lines.append(item["designation"])
        if item.get("qualification"):
            bio_lines.append(item["qualification"])
        if item.get("extra"):
            bio_lines.append(item["extra"])
        bio = " | ".join(bio_lines)

        user, u_created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "email": f"{username}@chanakyauniversity.edu.in",
                "is_staff": False,
            }
        )
        if u_created:
            user.set_password("chanakya@2025")
            user.save()

        # Update or create profile
        profile, p_created = Profile.objects.update_or_create(
            user=user,
            defaults={
                "role": "faculty",
                "department": dept,
                "bio": bio,
                "research_interests": f"Research specializations in {dept.name} and interdisciplinary initiatives at {dept.school.name}.",
                "personal_website": item.get("profile_url", ""),
            }
        )
        # Assign topics
        profile.topics.set(topic_objs[:3])
        created_count += 1

    print(f"\n[DONE] Successfully synced {created_count} real Chanakya University faculty members into the database!")

if __name__ == '__main__':
    seed_real_chanakya_data()
