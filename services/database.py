"""SQLite persistence layer (async, via aiosqlite).

Owns schema creation and raw queries. `agents/database_agent.py` wraps this
in the higher-level `DatabaseAgent` used by the coordinator.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from models.schemas import AnalysisRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_name TEXT,
    job_title TEXT,
    company_name TEXT,
    ats_score REAL NOT NULL,
    resume_path TEXT,
    jd_path TEXT,
    report_path TEXT,
    report_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_created_at ON analysis_history (created_at);
CREATE INDEX IF NOT EXISTS idx_history_company ON analysis_history (company_name);
"""


def _db_path() -> str:
    path = os.getenv("DATABASE_PATH", "data/ats_history.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


async def init_db() -> None:
    async with aiosqlite.connect(_db_path()) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def save_analysis(
    *,
    candidate_name: str | None,
    job_title: str | None,
    company_name: str | None,
    ats_score: float,
    resume_path: str | None,
    jd_path: str | None,
    report_path: str | None,
    report_json: dict,
) -> int:
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            """
            INSERT INTO analysis_history
                (candidate_name, job_title, company_name, ats_score,
                 resume_path, jd_path, report_path, report_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_name,
                job_title,
                company_name,
                ats_score,
                resume_path,
                jd_path,
                report_path,
                json.dumps(report_json),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def list_history(limit: int = 50, search: str | None = None) -> list[AnalysisRecord]:
    query = """
        SELECT id, candidate_name, job_title, company_name, ats_score,
               resume_path, jd_path, report_path, created_at
        FROM analysis_history
    """
    params: list = []
    if search:
        query += """
        WHERE candidate_name LIKE ? OR job_title LIKE ? OR company_name LIKE ?
        """
        like = f"%{search}%"
        params.extend([like, like, like])
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(query, params)

    return [
        AnalysisRecord(
            id=row["id"],
            candidate_name=row["candidate_name"],
            job_title=row["job_title"],
            company_name=row["company_name"],
            ats_score=row["ats_score"],
            resume_path=row["resume_path"],
            jd_path=row["jd_path"],
            report_path=row["report_path"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in rows
    ]


async def get_report(record_id: int) -> dict | None:
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        rows = list(await db.execute_fetchall(
            "SELECT * FROM analysis_history WHERE id = ?", (record_id,)
        ))
    if not rows:
        return None
    record = dict(rows[0])
    record["report_json"] = json.loads(record["report_json"]) if record["report_json"] else None
    return record
