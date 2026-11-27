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
from trends.models import ActivityEvent, ModerationFlag, TopicTrend

logger = logging.getLogger(__name__)
User = get_user_model()


class StarSchemaETLService:
    """Extracts, transforms, and exports Star-Schema Parquet files for DuckDB analytical querying."""

    @classmethod
    def run_etl(cls, out_dir: Optional[Path] = None) -> Dict[str, str]:
        """Generates dim_department, dim_user, dim_topic, dim_time, and fact_activity Parquet files."""
        target_dir = out_dir or settings.ANALYTICS_DATA_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        paths = {}

        # 1. DIM_DEPARTMENT
        departments = Department.objects.select_related("school").all()
        dept_rows = []
        valid_dept_ids = set()
        for d in departments:
            valid_dept_ids.add(d.id)
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
            valid_dept_ids.add(1)
        default_dept_id = next(iter(valid_dept_ids))
        paths["dim_department"] = cls._write_and_upload_parquet(
            pa.Table.from_pylist(dept_rows), "dim_department.parquet", target_dir
        )

        # 2. DIM_USER
        users = User.objects.select_related("profile", "profile__department").all()
        user_rows = []
        valid_user_ids = set()
        for u in users:
            prof = getattr(u, "profile", None)
            valid_user_ids.add(u.id)
            user_rows.append({
                "user_id": u.id,
                "username": u.username,
                "full_name": u.get_full_name() or u.username,
                "email": u.email,
                "role": prof.role if prof else "student",
                "department_id": prof.department_id if (prof and prof.department_id in valid_dept_ids) else default_dept_id,
                "is_active": u.is_active,
            })
        # Always ensure guest user 0 exists so anonymous activities join cleanly
        user_rows.append({
            "user_id": 0,
            "username": "guest_researcher",
            "full_name": "Guest Researcher",
            "email": "guest@chanakya.edu.in",
            "role": "student",
            "department_id": default_dept_id,
            "is_active": False,
        })
        valid_user_ids.add(0)
        paths["dim_user"] = cls._write_and_upload_parquet(
            pa.Table.from_pylist(user_rows), "dim_user.parquet", target_dir
        )

        # 3. DIM_TOPIC
        topics = Topic.objects.all()
        topic_rows = []
        valid_topic_ids = set()
        topic_name_map = {}
        for t in topics:
            valid_topic_ids.add(t.id)
            topic_name_map[t.name.lower()] = t.id
            topic_rows.append({
                "topic_id": t.id,
                "name": t.name,
                "description": t.description or "",
            })
        if not topic_rows:
            topic_rows.append({"topic_id": 1, "name": "Artificial Intelligence", "description": "AI & ML"})
            valid_topic_ids.add(1)
            topic_name_map["artificial intelligence"] = 1
        default_topic_id = next(iter(valid_topic_ids))
        paths["dim_topic"] = cls._write_and_upload_parquet(
            pa.Table.from_pylist(topic_rows), "dim_topic.parquet", target_dir
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
            dept_id = prof.department_id if (prof and prof.department_id in valid_dept_ids) else default_dept_id

            # Extract topic_id cleanly
            raw_top = ev.metadata.get("topic_id") if isinstance(ev.metadata, dict) else None
            topic_id = int(raw_top) if (raw_top and str(raw_top).isdigit() and int(raw_top) in valid_topic_ids) else None
            if not topic_id and isinstance(ev.metadata, dict):
                raw_name = ev.metadata.get("topic")
                if raw_name and raw_name.lower() in topic_name_map:
                    topic_id = topic_name_map[raw_name.lower()]
            if not topic_id:
                topic_id = default_topic_id

            user_id = ev.user_id if (ev.user_id and ev.user_id in valid_user_ids) else 0
            paper_id = int(ev.target_id) if (ev.target_type == "paper" and ev.target_id and ev.target_id.isdigit()) else 0

            fact_rows.append({
                "event_id": ev.id,
                "user_id": user_id,
                "department_id": dept_id,
                "topic_id": topic_id,
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
            pa.Table.from_pylist(time_rows), "dim_time.parquet", target_dir
        )
        paths["fact_activity"] = cls._write_and_upload_parquet(
            pa.Table.from_pylist(fact_rows), "fact_activity.parquet", target_dir
        )

        return paths

    @classmethod
    def _write_and_upload_parquet(cls, table: pa.Table, filename: str, target_dir: Optional[Path] = None) -> str:
        out_dir = target_dir or settings.ANALYTICS_DATA_DIR
        local_path = out_dir / filename
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="snappy")
        data_bytes = buf.getvalue()
        local_path.write_bytes(data_bytes)
        if out_dir == settings.ANALYTICS_DATA_DIR:
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

    @classmethod
    def get_top_departments_ranking(cls) -> List[Dict[str, Any]]:
        """1. Top departments ranking (Horizontal Bar Chart) aggregating fact_activity by department."""
        con = cls._get_connection()
        query = """
            SELECT 
                d.name as department_name,
                d.code as department_code,
                d.school_name,
                COUNT(f.event_id) as total_activity,
                SUM(CASE WHEN f.event_type = 'save_paper' THEN 1 ELSE 0 END) as save_count,
                SUM(CASE WHEN f.event_type = 'search' THEN 1 ELSE 0 END) as search_count,
                SUM(CASE WHEN f.event_type IN ('create_post', 'comment') THEN 1 ELSE 0 END) as discussion_count
            FROM dim_department d
            JOIN fact_activity f ON d.department_id = f.department_id
            GROUP BY d.department_id, d.name, d.code, d.school_name
            ORDER BY total_activity DESC
            LIMIT 15
        """
        df = con.execute(query).fetchdf()
        con.close()
        return df.to_dict(orient="records")

    @classmethod
    def get_student_vs_faculty_topics(cls) -> List[Dict[str, Any]]:
        """2. Top Student vs. Faculty Topics (Grouped Bar Chart) comparing role engagement per topic."""
        con = cls._get_connection()
        query = """
            SELECT 
                t.name as topic_name, 
                SUM(CASE WHEN u.role = 'student' THEN 1 ELSE 0 END) as student_activity,
                SUM(CASE WHEN u.role IN ('faculty', 'researcher') THEN 1 ELSE 0 END) as faculty_activity,
                COUNT(*) as total_activity
            FROM fact_activity f
            JOIN dim_topic t ON f.topic_id = t.topic_id
            JOIN dim_user u ON f.user_id = u.user_id
            GROUP BY t.topic_id, t.name
            ORDER BY total_activity DESC
            LIMIT 10
        """
        df = con.execute(query).fetchdf()
        con.close()
        return df.to_dict(orient="records")

    @classmethod
    def get_cross_department_collaboration_network(cls) -> Dict[str, Any]:
        """3. Cross-Department Collaboration Network Graph (node-link dataset)."""
        matrix_rows = cls.get_cross_department_collaboration_matrix()
        dept_ranking = cls.get_top_departments_ranking()
        dept_activity = {d["department_name"]: d["total_activity"] for d in dept_ranking}

        dept_school_map = {}
        for d in Department.objects.select_related("school").all():
            dept_school_map[d.name] = d.school.name if d.school else "General"

        school_colors = {
            "School of Biosciences": "#10b981",
            "Centre for Indian Knowledge Systems": "#c18e0e",
            "School of Management Sciences": "#3b82f6",
            "School of Engineering": "#6366f1",
            "School of Law, Governance and Public Policy": "#8b5cf6",
            "School of Mathematics and Natural Sciences": "#ec4899",
            "School of Arts, Humanities and Social Sciences": "#f97316",
        }

        nodes = []
        edges = []
        node_ids = {}
        idx = 1

        all_depts = set()
        for row in matrix_rows:
            all_depts.add(row["dept_from"])
            all_depts.add(row["dept_to"])

        if not all_depts:
            for d in dept_ranking[:6]:
                all_depts.add(d["department_name"])

        for d in all_depts:
            node_ids[d] = idx
            school = dept_school_map.get(d, "Chanakya School")
            color = school_colors.get(school, "#042863")
            activity = dept_activity.get(d, 50)
            size = max(16, min(38, int(14 + (activity ** 0.5) * 1.5)))
            nodes.append({
                "id": idx,
                "label": d,
                "title": f"<b>{d}</b><br>School: {school}<br>Activity Events: {activity}",
                "color": {"background": color, "border": "#ffffff", "highlight": {"background": "#c18e0e", "border": "#042863"}},
                "size": size,
                "font": {"size": 11, "color": "#1a202c", "face": "Inter, sans-serif"},
                "shape": "dot",
            })
            idx += 1

        for row in matrix_rows:
            f_id = node_ids.get(row["dept_from"])
            t_id = node_ids.get(row["dept_to"])
            if f_id and t_id and f_id != t_id:
                weight = row["interactions"]
                edges.append({
                    "from": f_id,
                    "to": t_id,
                    "value": weight,
                    "width": max(1, min(7, int(weight * 1.2))),
                    "title": f"{row['dept_from']} &harr; {row['dept_to']}: {weight} collaboration links",
                    "color": {"color": "#94a3b8", "highlight": "#c18e0e", "opacity": 0.75},
                })

        return {"nodes": nodes, "edges": edges}

    @classmethod
    def get_cross_department_collaboration_heatmap(cls) -> Dict[str, Any]:
        """3. Cross-Department Collaboration Heatmap (6x6 matrix) across primary university schools/departments."""
        depts = [
            "CSE & AI",
            "Data Science",
            "Biotech",
            "Math & Computing",
            "Public Policy",
            "Env. Science",
        ]
        dept_keywords = {
            "CSE & AI": ["computer", "cse", "csai"],
            "Data Science": ["data science", "analytics", "dsa"],
            "Biotech": ["bio", "btbi", "btbs"],
            "Math & Computing": ["math", "mc", "computing"],
            "Public Policy": ["policy", "governance", "ppg"],
            "Env. Science": ["env", "esst"],
        }

        def match_dept(name: str) -> Optional[str]:
            low = name.lower()
            for d, kws in dept_keywords.items():
                if any(k in low for k in kws):
                    return d
            return None

        matrix_rows = cls.get_cross_department_collaboration_matrix()

        direct_counts: Dict[Tuple[str, str], int] = {(d1, d2): 0 for d1 in depts for d2 in depts}
        for r in matrix_rows:
            d1 = match_dept(r.get("dept_from", ""))
            d2 = match_dept(r.get("dept_to", ""))
            if d1 and d2:
                direct_counts[(d1, d2)] += r["interactions"]

        grid_rows = []
        for r_dept in depts:
            cells = []
            for c_dept in depts:
                if r_dept == c_dept:
                    cells.append({
                        "col_dept": c_dept,
                        "value": None,
                        "display": "—",
                        "bg_color": "#f8fafc",
                        "text_color": "#94a3b8",
                        "border": "1px solid #e2e8f0",
                        "tooltip": f"{r_dept}: Department Core Baseline",
                    })
                else:
                    val = direct_counts.get((r_dept, c_dept), 0)
                    if val == 0:
                        bg_color = "#f1f5f9"
                        text_color = "#94a3b8"
                        border = "1px solid #e2e8f0"
                    elif val < 30:  # Low
                        bg_color = "#e0f2fe"
                        text_color = "#0369a1"
                        border = "1px solid #bae6fd"
                    elif val < 60:  # Moderate
                        bg_color = "#38bdf8"
                        text_color = "#082f49"
                        border = "1px solid #0284c7"
                    elif val < 85:  # High
                        bg_color = "#0284c7"
                        text_color = "#ffffff"
                        border = "1px solid #0369a1"
                    else:  # Intensive (>= 85, e.g. 92)
                        bg_color = "#042863"
                        text_color = "#c18e0e"
                        border = "2px solid #c18e0e"

                    cells.append({
                        "col_dept": c_dept,
                        "value": val,
                        "display": str(val),
                        "bg_color": bg_color,
                        "text_color": text_color,
                        "border": border,
                        "tooltip": f"{r_dept} ↔ {c_dept}: {val} shared research interactions",
                    })
            grid_rows.append({
                "row_dept": r_dept,
                "cells": cells,
            })

        apex_series = []
        for row in grid_rows:
            series_data = []
            for cell in row["cells"]:
                val = cell["value"] if cell["value"] is not None else 0
                series_data.append({
                    "x": cell["col_dept"],
                    "y": val,
                })
            apex_series.append({
                "name": row["row_dept"],
                "data": series_data,
            })

        return {
            "departments": depts,
            "grid_rows": grid_rows,
            "apex_series": apex_series,
        }

    @classmethod
    def get_monthly_activity_velocity(
        cls,
        selected_dept_id: Optional[int] = None,
        selected_topic_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """4. Monthly Activity & Topic Velocity (Line Chart) from dim_time with drill-down filters."""
        con = cls._get_connection()
        where_clauses = []
        if selected_dept_id:
            where_clauses.append(f"f.department_id = {selected_dept_id}")
        if selected_topic_id:
            where_clauses.append(f"f.topic_id = {selected_topic_id}")
        where_str = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        query = f"""
            SELECT 
                tm.year,
                tm.month,
                tm.month_name,
                CONCAT(tm.month_name, ' ', CAST(tm.year AS VARCHAR)) as label,
                COUNT(*) as total_events,
                COUNT(DISTINCT f.user_id) as active_users,
                COUNT(DISTINCT f.topic_id) as active_topics
            FROM fact_activity f
            JOIN dim_time tm ON f.time_id = tm.time_id
            {where_str}
            GROUP BY tm.year, tm.month, tm.month_name
            ORDER BY tm.year ASC, tm.month ASC
        """
        df = con.execute(query).fetchdf()
        con.close()
        return df.to_dict(orient="records")

    @classmethod
    def get_trend_anomaly_summary(cls) -> Dict[str, Any]:
        """5. Anomaly & Trend Alert Card (F7 integration) summarizing Z-score spikes and moderation flags."""
        from trends.models import ModerationFlag, TopicTrend
        spikes_qs = TopicTrend.objects.filter(is_spike=True).select_related("topic").order_by("-z_score")
        spikes = []
        for s in spikes_qs[:6]:
            spikes.append({
                "topic_id": s.topic_id,
                "topic_name": s.topic.name,
                "z_score": round(s.z_score, 2),
                "growth_rate": round(s.growth_rate, 1),
                "current_count": s.current_count,
                "baseline_count": round(s.baseline_count, 1),
            })

        flag_count = ModerationFlag.objects.filter(status="pending").count()
        return {
            "spikes": spikes,
            "spike_count": len(spikes),
            "flag_count": flag_count,
            "has_alerts": bool(spikes or flag_count > 0),
        }

