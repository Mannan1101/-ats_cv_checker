"""Cover Letter Agent.

Generates a tailored, professional cover letter from the candidate's real
resume data and the target job/company -- same truthfulness constraints as
the Resume Improvement Agent.
"""

from __future__ import annotations

import json

from agents import Agent

from models.schemas import (
    CoverLetter,
    CoverLetterRequest,
    JobRequirements,
    ParsedResume,
)
from services.llm_client import default_model_settings, get_model, json_schema_instructions, run_structured

INSTRUCTIONS = """\
You are an expert career coach writing a tailored cover letter. Use only
real details from the candidate's resume -- do not invent experience,
employers, or skills.

Structure:
- greeting: e.g. "Dear Hiring Manager," or "Dear {name}," if given
- opening_paragraph: hook + the role being applied for + one standout
  qualification
- body_paragraphs: 1-2 paragraphs connecting the candidate's real
  experience/projects to the job's key responsibilities and required
  skills
- closing_paragraph: enthusiasm, call to action, thanks
- signature: e.g. "Sincerely,\\n{candidate name}"
- full_text: the complete letter assembled from the parts above, ready to
  send as-is (proper spacing/line breaks between paragraphs)

Keep the tone professional, confident, and concise (under ~350 words for
the full letter).
"""

cover_letter_agent = Agent(
    name="Cover Letter Agent",
    instructions=INSTRUCTIONS + json_schema_instructions(CoverLetter),
    model=get_model(),
    model_settings=default_model_settings(),
)


def _build_prompt(resume: ParsedResume, jd: JobRequirements, request: CoverLetterRequest) -> str:
    payload = {
        "candidate_name": resume.contact_info.full_name,
        "company_name": request.company_name,
        "job_title": request.job_title,
        "hiring_manager": request.hiring_manager,
        "professional_summary": resume.professional_summary,
        "skills": resume.skills,
        "work_experience": [e.model_dump() for e in resume.work_experience],
        "projects": [p.model_dump() for p in resume.projects],
        "job_responsibilities": jd.responsibilities,
        "job_required_skills": jd.required_skills,
    }
    return "Cover letter request data (JSON):\n\n" + json.dumps(payload, indent=2)


async def generate_cover_letter(
    resume: ParsedResume, jd: JobRequirements, request: CoverLetterRequest
) -> CoverLetter:
    return await run_structured(cover_letter_agent, _build_prompt(resume, jd, request), CoverLetter)
