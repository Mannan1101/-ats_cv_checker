"""ATS CV Checker & Optimizer -- FastAPI service.

Endpoints:
    POST /analyze       Full pipeline (parse -> JD analysis -> ATS score -> improve -> export -> save)
    POST /improve        Resume parsing + JD analysis + improvement only (no export/db/cover letter)
    POST /cover-letter    Generate a cover letter from a resume + job/company info
    GET  /history         List past analyses from SQLite
    GET  /report/{id}     Fetch one stored analysis report by id
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

if sys.platform == "win32":
    # See main.py: avoid cp1252 UnicodeEncodeError on LLM-generated text.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ats_agents import database_agent
from ats_agents.ats_analyzer import analyze_ats_fit
from ats_agents.coordinator import run_pipeline
from ats_agents.cover_letter import generate_cover_letter
from ats_agents.jd_analyzer import analyze_job_description
from ats_agents.resume_improver import improve_resume
from ats_agents.resume_parser import parse_resume
from models.schemas import CoverLetterRequest

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await database_agent.initialize()
    yield


app = FastAPI(
    title="ATS CV Checker & Optimizer",
    description="Multi-agent resume analysis, scoring, and optimization API.",
    version="1.0.0",
    lifespan=lifespan,
)


async def _save_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "resume").suffix or ".txt"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    content = await upload.read()
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


@app.post("/analyze")
async def analyze_endpoint(
    resume: UploadFile = File(..., description="Resume file: PDF, DOCX, or TXT"),
    job_description: str = Form(..., description="Job description text, or leave a file-based JD as raw text"),
    company_name: str | None = Form(None),
    job_title: str | None = Form(None),
    hiring_manager: str | None = Form(None),
    generate_cover_letter: bool = Form(True),
    output_dir: str = Form("exports"),
) -> JSONResponse:
    resume_path = await _save_upload(resume)
    try:
        result = await run_pipeline(
            resume_path=resume_path,
            jd_text_or_path=job_description,
            output_dir=output_dir,
            company_name=company_name,
            job_title=job_title,
            hiring_manager=hiring_manager,
            generate_cover_letter_flag=generate_cover_letter,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        resume_path.unlink(missing_ok=True)

    return JSONResponse(content=result.model_dump(mode="json"))


@app.post("/improve")
async def improve_endpoint(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
) -> JSONResponse:
    resume_path = await _save_upload(resume)
    try:
        parsed_resume = await parse_resume(resume_path)
        jd = await analyze_job_description(job_description)
        ats_report = await analyze_ats_fit(parsed_resume, jd)
        improved = await improve_resume(parsed_resume, jd, ats_report)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        resume_path.unlink(missing_ok=True)

    return JSONResponse(content=improved.model_dump(mode="json"))


@app.post("/cover-letter")
async def cover_letter_endpoint(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
    company_name: str = Form(...),
    job_title: str = Form(...),
    hiring_manager: str | None = Form(None),
) -> JSONResponse:
    resume_path = await _save_upload(resume)
    try:
        parsed_resume = await parse_resume(resume_path)
        jd = await analyze_job_description(job_description)
        letter = await generate_cover_letter(
            parsed_resume,
            jd,
            CoverLetterRequest(
                company_name=company_name, job_title=job_title, hiring_manager=hiring_manager
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        resume_path.unlink(missing_ok=True)

    return JSONResponse(content=letter.model_dump(mode="json"))


@app.get("/history")
async def history_endpoint(limit: int = 50, search: str | None = None) -> JSONResponse:
    records = await database_agent.get_history(limit=limit, search=search)
    return JSONResponse(content=[r.model_dump(mode="json") for r in records])


@app.get("/report/{record_id}")
async def report_endpoint(record_id: int) -> JSONResponse:
    record = await database_agent.get_report_by_id(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No report found with id {record_id}")
    return JSONResponse(content=record)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
