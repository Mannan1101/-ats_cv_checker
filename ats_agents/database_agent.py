"""Database Agent.

Thin, purpose-specific wrapper around `services.database` -- persists each
analysis run and provides history/search for the CLI and API. No LLM calls;
"agent" here means "the component responsible for this concern," matching
the rest of the multi-agent architecture.
"""

from __future__ import annotations

from models.schemas import ATSAnalysisReport, AnalysisRecord, JobRequirements, ParsedResume
from services import database


async def initialize() -> None:
    await database.init_db()


async def record_analysis(
    resume: ParsedResume,
    jd: JobRequirements,
    report: ATSAnalysisReport,
    resume_path: str | None,
    jd_path: str | None,
    report_path: str | None,
) -> int:
    return await database.save_analysis(
        candidate_name=resume.contact_info.full_name,
        job_title=jd.job_title,
        company_name=jd.company_name,
        ats_score=report.ats_score,
        resume_path=resume_path,
        jd_path=jd_path,
        report_path=report_path,
        report_json=report.model_dump(),
    )


async def get_history(limit: int = 50, search: str | None = None) -> list[AnalysisRecord]:
    return await database.list_history(limit=limit, search=search)


async def get_report_by_id(record_id: int) -> dict | None:
    return await database.get_report(record_id)
