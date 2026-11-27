import random
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from accounts.models import Department, Profile, School, Topic
from papers.models import Paper
from trends.models import ActivityEvent, ModerationFlag, TopicTrend
from institutional_analytics.services import StarSchemaETLService

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Seeds rich, realistic research activity events (3,500+ events) across 6 schools, "
        "both academic roles, 8+ topics, and a 6-month timeline (June - Nov 2026) for the F9 Analytics Dashboard."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing synthetic activity events before seeding.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO("=== Seeding Realistic Analytics Graph Data ==="))

        # -------------------------------------------------------------
        # 1. Ensure the 6 University Schools & Departments
        # -------------------------------------------------------------
        school_dept_specs = [
            ("School of Technology & Computing", "STC", "Computer Science & Engineering", "CSE"),
            ("School of Technology & Computing", "STC", "Data Science & Analytics", "DSA"),
            ("School of Biosciences", "SBS", "Biotechnology & Biosciences", "BTBS"),
            ("School of Mathematics and Natural Sciences", "SMNS", "Mathematics & Computing", "MTH"),
            ("School of Law, Governance and Public Policy", "SLGPP", "Public Policy & Governance", "PPG"),
            ("School of Sustainable Development & Policy", "SSDP", "Environmental Sciences", "ENV"),
        ]

        depts = []
        for school_name, school_code, dept_name, dept_code in school_dept_specs:
            school, _ = School.objects.get_or_create(
                name=school_name,
                defaults={"code": school_code, "description": f"{school_name} at Chanakya University"},
            )
            dept, _ = Department.objects.get_or_create(
                name=dept_name,
                defaults={"code": dept_code, "school": school, "description": f"{dept_name} Academic Division"},
            )
            if dept.school != school:
                dept.school = school
                dept.save(update_fields=["school"])
            depts.append(dept)

        self.stdout.write(self.style.SUCCESS(f"Verified {len(depts)} Academic Departments across Chanakya University."))

        # -------------------------------------------------------------
        # 2. Ensure 8+ Key Research Topics
        # -------------------------------------------------------------
        target_topics = [
            "Deep Learning",
            "Machine Learning",
            "Genomics & Bioinformatics",
            "Quantum Computing",
            "Responsible AI",
            "Cybersecurity",
            "Sustainable Energy",
            "Public Policy",
        ]
        topic_objs = []
        for tname in target_topics:
            t, _ = Topic.objects.get_or_create(
                name=tname,
                defaults={"description": f"Scholarly research focus on {tname}"},
            )
            topic_objs.append(t)

        self.stdout.write(self.style.SUCCESS(f"Verified {len(topic_objs)} Research Topics."))

        # -------------------------------------------------------------
        # 3. Ensure Academic Users Across All 6 Departments and Roles
        # -------------------------------------------------------------
        student_users = []
        faculty_users = []

        # Create or update realistic user cohorts
        user_names_student = [
            ("arjun.patel", "Arjun", "Patel"),
            ("priya.sharma", "Priya", "Sharma"),
            ("rohan.verma", "Rohan", "Verma"),
            ("ananya.iyer", "Ananya", "Iyer"),
            ("sneha.rao", "Sneha", "Rao"),
            ("kavita.nair", "Kavita", "Nair"),
            ("rahul.deshmukh", "Rahul", "Deshmukh"),
            ("manish.bose", "Manish", "Bose"),
            ("tanvi.kulkarni", "Tanvi", "Kulkarni"),
            ("aditya.menon", "Aditya", "Menon"),
            ("divya.joshi", "Divya", "Joshi"),
            ("varun.singh", "Varun", "Singh"),
        ]

        user_names_faculty = [
            ("prof.vikram.malhotra", "Vikram", "Malhotra"),
            ("dr.neha.gupta", "Neha", "Gupta"),
            ("dr.suresh.kumar", "Suresh", "Kumar"),
            ("prof.rhea.banerjee", "Rhea", "Banerjee"),
            ("dr.amit.bhat", "Amit", "Bhat"),
            ("dr.meenakshi.sundaram", "Meenakshi", "Sundaram"),
            ("prof.rajesh.shetty", "Rajesh", "Shetty"),
            ("dr.deepa.venkatesh", "Deepa", "Venkatesh"),
            ("dr.karan.kulkarni", "Karan", "Kulkarni"),
            ("prof.lakshmi.narayan", "Lakshmi", "Narayan"),
            ("dr.vinay.hegde", "Vinay", "Hegde"),
            ("dr.anita.desai", "Anita", "Desai"),
        ]

        for idx, (uname, fname, lname) in enumerate(user_names_student):
            u, _ = User.objects.get_or_create(
                username=uname,
                defaults={"first_name": fname, "last_name": lname, "email": f"{uname}@chanakya.edu.in"}
            )
            dept = depts[idx % len(depts)]
            prof, _ = Profile.objects.get_or_create(
                user=u,
                defaults={"role": "student", "department": dept, "bio": f"Graduate Student Researcher in {dept.name}."}
            )
            if prof.role != "student" or prof.department != dept:
                prof.role = "student"
                prof.department = dept
                prof.save()
            student_users.append(u)

        for idx, (uname, fname, lname) in enumerate(user_names_faculty):
            u, _ = User.objects.get_or_create(
                username=uname,
                defaults={"first_name": fname, "last_name": lname, "email": f"{uname}@chanakya.edu.in"}
            )
            dept = depts[idx % len(depts)]
            prof, _ = Profile.objects.get_or_create(
                user=u,
                defaults={"role": "faculty", "department": dept, "bio": f"Faculty Researcher & Mentor in {dept.name}."}
            )
            if prof.role not in ("faculty", "researcher") or prof.department != dept:
                prof.role = "faculty"
                prof.department = dept
                prof.save()
            faculty_users.append(u)

        # Also collect other existing users
        for u in User.objects.filter(is_active=True).select_related("profile", "profile__department"):
            if not hasattr(u, "profile") or not u.profile:
                continue
            if u.profile.role == "student" and u not in student_users:
                student_users.append(u)
            elif u.profile.role in ("faculty", "researcher") and u not in faculty_users:
                faculty_users.append(u)

        self.stdout.write(self.style.SUCCESS(
            f"Active cohorts: {len(student_users)} Students, {len(faculty_users)} Faculty/Researchers."
        ))

        # -------------------------------------------------------------
        # 4. Generate 3,600+ Realistic Research Activity Events
        # -------------------------------------------------------------
        papers = list(Paper.objects.all()[:150])

        # Monthly event distribution (Upward trajectory from June to November 2026)
        month_targets = [
            (2026, 6, 320),   # June: 320 events
            (2026, 7, 420),   # July: 420 events
            (2026, 8, 540),   # August: 540 events
            (2026, 9, 680),   # September: 680 events
            (2026, 10, 850),  # October: 850 events
            (2026, 11, 1100), # November: 1100 events
        ]

        # Department weight bias for stacked bars
        dept_weights = {
            "Computer Science & Engineering": 1.4,
            "Data Science & Analytics": 1.2,
            "Biotechnology & Biosciences": 1.0,
            "Mathematics & Computing": 0.85,
            "Public Policy & Governance": 0.70,
            "Environmental Sciences": 0.65,
        }

        # Event types with realistic breakdown
        event_types = ["save_paper", "search", "create_post", "comment", "view_paper"]
        event_weights = [0.28, 0.34, 0.12, 0.12, 0.14]

        new_events = []
        random.seed(42)

        for year, month, target_count in month_targets:
            days_in_month = 30 if month in (6, 9, 11) else 31
            for _ in range(target_count):
                day = random.randint(1, min(days_in_month, 27 if (year == 2026 and month == 11) else days_in_month))
                hour = random.randint(8, 22)
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                timestamp = timezone.make_aware(datetime(year, month, day, hour, minute, second))

                # Role selection (55% student, 45% faculty)
                is_student = random.random() < 0.55
                user_pool = student_users if is_student else faculty_users
                user = random.choice(user_pool)
                user_dept = user.profile.department if (user.profile and user.profile.department) else random.choice(depts)

                # Topic selection
                topic = random.choice(topic_objs)

                # Event type
                ev_type = random.choices(event_types, weights=event_weights)[0]

                # Target
                target_type = "topic"
                target_id = str(topic.id)
                meta = {
                    "topic_id": topic.id,
                    "topic": topic.name,
                    "department_id": user_dept.id,
                    "department": user_dept.name,
                    "role": user.profile.role,
                }

                if ev_type in ("save_paper", "view_paper") and papers:
                    paper = random.choice(papers)
                    target_type = "paper"
                    target_id = str(paper.id)
                    meta["paper_id"] = paper.id
                    meta["title"] = paper.title
                elif ev_type == "search":
                    target_type = "query"
                    target_id = f"q_{topic.id}"
                    meta["query"] = f"recent advancements in {topic.name}"
                elif ev_type in ("create_post", "comment"):
                    target_type = "discussion"
                    target_id = f"disc_{random.randint(1, 200)}"
                    meta["tag"] = topic.name

                ev = ActivityEvent(
                    user=user,
                    event_type=ev_type,
                    target_type=target_type,
                    target_id=target_id,
                    metadata=meta,
                    timestamp=timestamp,
                )
                new_events.append(ev)

        # Bulk create all new events
        ActivityEvent.objects.bulk_create(new_events, batch_size=500)
        total_evs = ActivityEvent.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"Inserted {len(new_events)} realistic research events. Total ActivityEvents in DB: {total_evs}."
        ))

        # -------------------------------------------------------------
        # 5. Ensure Active Topic Spikes & Moderation Flags (F7)
        # -------------------------------------------------------------
        # Spikes for Deep Learning, Genomics, Quantum Computing
        spike_configs = [
            ("Deep Learning", 14.8, 125.0, 480, 210.0),
            ("Genomics & Bioinformatics", 8.4, 95.0, 310, 160.0),
            ("Quantum Computing", 5.7, 72.0, 240, 140.0),
            ("Cybersecurity", 3.2, 45.0, 180, 120.0),
        ]
        for tname, z, growth, curr, base in spike_configs:
            t = Topic.objects.filter(name=tname).first()
            if t:
                TopicTrend.objects.update_or_create(
                    topic=t,
                    defaults={
                        "window_days": 7,
                        "current_count": curr,
                        "baseline_count": base,
                        "growth_rate": growth,
                        "z_score": z,
                        "is_spike": True,
                    }
                )

        # Moderation flags
        flag_samples = [
            ("arjun.patel", "High-frequency burst posting anomaly (6 posts in 4 minutes)", "high"),
            ("priya.sharma", "Automated query repetition anomaly from single session", "medium"),
            ("manish.bose", "Duplicate discussion thread flood flagged by spam detector", "low"),
        ]
        for uname, reason, sev in flag_samples:
            u = User.objects.filter(username=uname).first()
            if u:
                ModerationFlag.objects.get_or_create(
                    user=u,
                    flag_reason=reason,
                    defaults={"severity": sev, "status": "pending", "details": {"score": 0.88}}
                )

        self.stdout.write(self.style.SUCCESS("F7 Topic Spikes & Moderation Flags verified."))

        # -------------------------------------------------------------
        # 6. Rebuild Star Schema Parquet Tables & MinIO Lakehouse Sync
        # -------------------------------------------------------------
        self.stdout.write(self.style.NOTICE("Rebuilding Star-Schema Parquet files with embedded DuckDB..."))
        paths = StarSchemaETLService.run_etl()
        for tbl, p in paths.items():
            self.stdout.write(self.style.SUCCESS(f"  - Synchronized {tbl} -> {p}"))

        self.stdout.write(self.style.SUCCESS("\n=== Analytics Seeding & Parquet Rebuild Complete ==="))
