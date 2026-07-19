"""Coordinator Agent.

Runs the full pipeline in a fixed, deterministic order:

    Resume Parser -> JD Analyzer -> ATS Analyzer -> Resume Improvement
    -> Cover Letter (optional) -> Export -> Database -> Result

The sequence itself is a fixed workflow (not something that benefits from
letting an LLM decide routing), so the coordinator is plain async Python
that calls each specialized agent module in order -- this keeps the
pipeline reliable, testable, and cheap to run against a free-tier model,
while every step still individually uses the OpenAI Agents SDK
(`Agent` + `Runner` + structured `output_type`s).
"""

from __future__ import annotations

import logging
from pathlib import Path

from models.schemas import CoverLetterRequest, PipelineResult
from ats_agents import database_agent
from ats_agents.ats_analyzer import analyze_ats_fit
from ats_agents.cover_letter import generate_cover_letter
from ats_agents.export_agent import export_all
from ats_agents.jd_analyzer import analyze_job_description
from ats_agents.resume_improver import improve_resume
from ats_agents.resume_parser import parse_resume

logger = logging.getLogger(__name__)


async def run_pipeline(
    resume_path: str | Path,
    jd_text_or_path: str,
    output_dir: str | Path,
    *,
    company_name: str | None = None,
    job_title: str | None = None,
    hiring_manager: str | None = None,
    generate_cover_letter_flag: bool = True,
    save_to_db: bool = True,
) -> PipelineResult:
    """Run the entire ATS analysis + optimization pipeline end to end."""
    output_dir = Path(output_dir)

    logger.info("Step 1/6: Parsing resume %s", resume_path)
    resume = await parse_resume(resume_path)

    logger.info("Step 2/6: Analyzing job description")
    jd = await analyze_job_description(jd_text_or_path)
    if company_name:
        jd.company_name = company_name
    if job_title:
        jd.job_title = job_title

    logger.info("Step 3/6: Computing ATS fit")
    ats_report = await analyze_ats_fit(resume, jd)

    logger.info("Step 4/6: Generating resume improvements")
    improved = await improve_resume(resume, jd, ats_report)

    cover_letter = None
    if generate_cover_letter_flag and jd.company_name and jd.job_title:
        logger.info("Step 5/6: Generating cover letter")
        cover_letter = await generate_cover_letter(
            resume,
            jd,
            CoverLetterRequest(
                company_name=jd.company_name,
                job_title=jd.job_title,
                hiring_manager=hiring_manager,
            ),
        )
    else:
        logger.info("Step 5/6: Skipped cover letter (no company_name/job_title available)")

    logger.info("Step 6/6: Exporting files and saving to database")
    exported_files = export_all(resume, jd, ats_report, improved, output_dir, cover_letter)

    record_id = None
    if save_to_db:
        await database_agent.initialize()
        jd_path = jd_text_or_path if Path(jd_text_or_path).exists() else None
        record_id = await database_agent.record_analysis(
            resume=resume,
            jd=jd,
            report=ats_report,
            resume_path=str(resume_path),
            jd_path=jd_path,
            report_path=exported_files.get("markdown_report"),
        )

    return PipelineResult(
        parsed_resume=resume,
        job_requirements=jd,
        ats_report=ats_report,
        improved_resume=improved,
        cover_letter=cover_letter,
        exported_files=exported_files,
        record_id=record_id,
    )
