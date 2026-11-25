import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Department, Profile, School, Topic
from discussions.models import Comment, DiscussionPost
from papers.models import Paper
from papers.services import MinIOService
from research_library.models import ResearchResource, SavedResearchItem
from trends.models import ActivityEvent

logger = logging.getLogger(__name__)
User = get_user_model()


class StarSchemaETLService:
    """Extracts, transforms, and exports Star-Schema Parquet files for DuckDB analytical querying."""

    @classmethod
    def run_etl(cls) -> Dict[str, str]:
        """Generates dim_department, dim_user, dim_topic, dim_time, and fact_activity Parquet files."""
        out_dir = settings.ANALYTICS_DATA_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = {}

        # 1. DIM_DEPARTMENT
        departments = Department.objects.select_related("school").all()
        dept_rows = []
        for d in departments:
            dept_rows.append({
                "department_id": d.id,
                "name": d.name,
                "code": d.code,
                "school_name": d.school.name if d.school else "General",
                "school_code": d.school.code if d.school else "GEN",
            })
        if not dept_rows:
            dept_rows.append({
                "department_id": 1,
                "name": "Computer Science & AI",
                "code": "CSAI",
                "school_name": "School of Computing",
                "school_code": "SC",
            })
        paths["dim_department"] = cls._write_and_upload_parquet(
            pa.Table.from_pylist(dept_rows), "dim_department.parquet"
        )

        # 2. DIM_USER
        users = User.objects.select_related("profile", "profile__department").all()
        user_rows = []
        for u in users:
            prof = getattr(u, "profile", None)
            user_rows.append({
                "user_id": u.id,
                "username": u.username,
                "full_name": u.get_full_name() or u.username,
                "email": u.email,
                "role": prof.role if prof else "student",
                "department_id": prof.department_id if (prof and prof.department_id) else 1,
                "is_active": u.is_active,
            })
        paths["dim_user"] = cls._write_and_upload_parquet(
            pa.Table.from_pylist(user_rows), "dim_user.parquet"
        )

        # 3. DIM_TOPIC
        topics = Topic.objects.all()
        topic_rows = []
        for t in topics:
            topic_rows.append({
                "topic_id": t.id,
                "name": t.name,
                "description": t.description or "",
            })
        if not topic_rows:
            topic_rows.append({"topic_id": 1, "name": "Artificial Intelligence", "description": "AI & ML"})
        paths["dim_topic"] = cls._write_and_upload_parquet(
            pa.Table.from_pylist(topic_rows), "dim_topic.parquet"
        )

        # 4. DIM_TIME & FACT_ACTIVITY
        events = ActivityEvent.objects.all().select_related("user", "user__profile")
        time_rows = []
        fact_rows = []
        time_seen = set()

        # Gather activity events
        for ev in events:
            t = ev.timestamp
            time_id = int(t.strftime("%Y%m%d%H"))
            if time_id not in time_seen:
                time_seen.add(time_id)
                time_rows.append({
                    "time_id": time_id,
                    "timestamp": t.isoformat(),
                    "date": t.strftime("%Y-%m-%d"),
                    "year": t.year,
                    "month": t.month,
                    "month_name": t.strftime("%b"),
                    "day": t.day,
                    "day_of_week": t.strftime("%A"),
                })

            user = ev.user
            prof = getattr(user, "profile", None) if user else None
            dept_id = prof.department_id if (prof and prof.department_id) else 1

            # Extract topic_id or paper_id if present in metadata
            topic_id = ev.metadata.get("topic_id") or 1
            paper_id = int(ev.target_id) if (ev.target_type == "paper" and ev.target_id.isdigit()) else 0

            fact_rows.append({
                "event_id": ev.id,
                "user_id": ev.user_id or 0,
                "department_id": dept_id,
                "topic_id": int(topic_id),
                "paper_id": paper_id,
                "time_id": time_id,
                "event_type": ev.event_type,
                "created_at": t.isoformat(),
            })

        # Also populate from DiscussionPosts and SavedResearchItems if event logs are sparse
        if len(fact_rows) < 5:
            now = timezone.now()
            time_id = int(now.strftime("%Y%m%d%H"))
            if time_id not in time_seen:
                time_rows.append({
                    "time_id": time_id,
                    "timestamp": now.isoformat(),
                    "date": now.strftime("%Y-%m-%d"),
                    "year": now.year,
                    "month": now.month,
                    "month_name": now.strftime("%b"),
                    "day": now.day,
                    "day_of_week": now.strftime("%A"),
                })
            for post in DiscussionPost.objects.all()[:100]:
                tag = post.tags.first()
                prof = getattr(post.author, "profile", None)
                fact_rows.append({
                    "event_id": 10000 + post.id,
                    "user_id": post.author_id,
                    "department_id": prof.department_id if (prof and prof.department_id) else 1,
                    "topic_id": tag.id if tag else 1,
                    "paper_id": 0,
                    "time_id": time_id,
                    "event_type": "create_post",
                    "created_at": post.created_at.isoformat(),
                })
            for s in SavedResearchItem.objects.all()[:100]:
                prof = getattr(s.user, "profile", None)
                fact_rows.append({
                    "event_id": 20000 + s.id,
                    "user_id": s.user_id,
                    "department_id": prof.department_id if (prof and prof.department_id) else 1,
                    "topic_id": 1,
                    "paper_id": 0,
                    "time_id": time_id,
                    "event_type": "save_paper",
                    "created_at": s.saved_at.isoformat(),
                })

        if not time_rows:
            now = timezone.now()
            time_rows.append({
                "time_id": 1,
                "timestamp": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "year": now.year,
                "month": now.month,
                "month_name": now.strftime("%b"),
                "day": now.day,
                "day_of_week": now.strftime("%A"),
            })
        if not fact_rows:
            fact_rows.append({
                "event_id": 1,
                "user_id": 1,
                "department_id": 1,
                "topic_id": 1,
                "paper_id": 0,
                "time_id": 1,
                "event_type": "view_paper",
                "created_at": timezone.now().isoformat(),
            })

        paths["dim_time"] = cls._write_and_upload_parquet(
            pa.Table.from_pylist(time_rows), "dim_time.parquet"
        )
        paths["fact_activity"] = cls._write_and_upload_parquet(
            pa.Table.from_pylist(fact_rows), "fact_activity.parquet"
        )

        return paths

    @classmethod
    def _write_and_upload_parquet(cls, table: pa.Table, filename: str) -> str:
        local_path = settings.ANALYTICS_DATA_DIR / filename
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="snappy")
        data_bytes = buf.getvalue()
        local_path.write_bytes(data_bytes)
        MinIOService.upload_parquet(f"star_schema/{filename}", data_bytes)
        return str(local_path)


class DuckDBAnalyticsService:
    """Executes star-schema analytical queries using DuckDB over exported Parquet files."""

    @classmethod
    def _get_connection(cls) -> duckdb.DuckDBPyConnection:
        # Check that parquet files exist; if not, run ETL
        fact_path = settings.ANALYTICS_DATA_DIR / "fact_activity.parquet"
        if not fact_path.exists():
            StarSchemaETLService.run_etl()

        con = duckdb.connect(database=":memory:")
        d = str(settings.ANALYTICS_DATA_DIR)
        con.execute(f"CREATE VIEW fact_activity AS SELECT * FROM read_parquet('{d}/fact_activity.parquet')")
        con.execute(f"CREATE VIEW dim_department AS SELECT * FROM read_parquet('{d}/dim_department.parquet')")
        con.execute(f"CREATE VIEW dim_user AS SELECT * FROM read_parquet('{d}/dim_user.parquet')")
        con.execute(f"CREATE VIEW dim_topic AS SELECT * FROM read_parquet('{d}/dim_topic.parquet')")
        con.execute(f"CREATE VIEW dim_time AS SELECT * FROM read_parquet('{d}/dim_time.parquet')")
        return con

    @classmethod
    def get_department_topics_over_time(cls) -> List[Dict[str, Any]]:
        """1. Research topics by department over time."""
        con = cls._get_connection()
        query = """
            SELECT 
                d.name as department,
                t.name as topic,
                tm.year,
                tm.month,
                tm.month_name,
                COUNT(*) as activity_count
            FROM fact_activity f
            JOIN dim_department d ON f.department_id = d.department_id
            JOIN dim_topic t ON f.topic_id = t.topic_id
            JOIN dim_time tm ON f.time_id = tm.time_id
            GROUP BY d.name, t.name, tm.year, tm.month, tm.month_name
            ORDER BY tm.year DESC, tm.month DESC, activity_count DESC
            LIMIT 50
        """
        df = con.execute(query).fetchdf()
        con.close()
        return df.to_dict(orient="records")

    @classmethod
    def get_cross_department_collaboration_matrix(cls) -> List[Dict[str, Any]]:
        """2. Cross-department collaboration & interaction matrix."""
        # Find comments where author's department interacts with post author's department
        comments = Comment.objects.select_related("author__profile__department", "post__author__profile__department").all()
        matrix: Dict[str, Dict[str, int]] = {}

        for c in comments:
            author_dept = getattr(getattr(c.author, "profile", None), "department", None)
            post_dept = getattr(getattr(c.post.author, "profile", None), "department", None)
            if author_dept and post_dept:
                d1 = author_dept.name
                d2 = post_dept.name
                if d1 not in matrix:
                    matrix[d1] = {}
                matrix[d1][d2] = matrix[d1].get(d2, 0) + 1

        rows = []
        for d1, targets in matrix.items():
            for d2, count in targets.items():
                rows.append({"dept_from": d1, "dept_to": d2, "interactions": count})

        rows.sort(key=lambda x: x["interactions"], reverse=True)
        return rows[:25]

    @classmethod
    def get_most_engaged_papers(cls) -> List[Dict[str, Any]]:
        """3. Most saved and most discussed papers + engagement trends."""
        papers = (
            Paper.objects.all()
            .order_by("-save_count", "-pagerank_score")[:15]
            .values("id", "title", "published_year", "venue", "save_count", "pagerank_score")
        )
        return list(papers)

    @classmethod
    def get_drill_down_stats(
        cls,
        selected_dept_id: Optional[int] = None,
        selected_topic_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """4. Interactive Drill-down: University -> Department -> Topic -> Member."""
        con = cls._get_connection()

        # 4a. University Overview
        univ_summary = con.execute("""
            SELECT 
                COUNT(*) as total_events,
                COUNT(DISTINCT user_id) as active_members,
                COUNT(DISTINCT department_id) as active_departments,
                COUNT(DISTINCT topic_id) as active_topics
            FROM fact_activity
        """).fetchdf().to_dict(orient="records")[0]

        # 4b. Department Breakdown
        dept_breakdown = con.execute("""
            SELECT 
                d.department_id,
                d.name as department_name,
                d.code as department_code,
                d.school_name,
                COUNT(f.event_id) as total_activity,
                COUNT(DISTINCT f.user_id) as member_count
            FROM dim_department d
            LEFT JOIN fact_activity f ON d.department_id = f.department_id
            GROUP BY d.department_id, d.name, d.code, d.school_name
            ORDER BY total_activity DESC
        """).fetchdf().to_dict(orient="records")

        # 4c. Topics in Department (if selected)
        topic_breakdown = []
        if selected_dept_id:
            topic_breakdown = con.execute(f"""
                SELECT 
                    t.topic_id,
                    t.name as topic_name,
                    COUNT(f.event_id) as topic_activity,
                    COUNT(DISTINCT f.user_id) as researchers_count
                FROM fact_activity f
                JOIN dim_topic t ON f.topic_id = t.topic_id
                WHERE f.department_id = {selected_dept_id}
                GROUP BY t.topic_id, t.name
                ORDER BY topic_activity DESC
            """).fetchdf().to_dict(orient="records")

        # 4d. Members in Topic (if selected)
        member_breakdown = []
        if selected_dept_id and selected_topic_id:
            member_breakdown = con.execute(f"""
                SELECT 
                    u.user_id,
                    u.username,
                    u.full_name,
                    u.role,
                    COUNT(f.event_id) as member_events
                FROM fact_activity f
                JOIN dim_user u ON f.user_id = u.user_id
                WHERE f.department_id = {selected_dept_id} AND f.topic_id = {selected_topic_id}
                GROUP BY u.user_id, u.username, u.full_name, u.role
                ORDER BY member_events DESC
                LIMIT 20
            """).fetchdf().to_dict(orient="records")

        con.close()

        return {
            "university": univ_summary,
            "departments": dept_breakdown,
            "topics": topic_breakdown,
            "members": member_breakdown,
            "selected_dept_id": selected_dept_id,
            "selected_topic_id": selected_topic_id,
        }

