"""Resume Improvement Agent.

Rewrites weak wording, strengthens the summary/skills/bullets, and
recommends missing keywords -- without ever fabricating experience,
employers, dates, or certifications the candidate does not have.
"""

from __future__ import annotations

import json

from agents import Agent

from models.schemas import ATSAnalysisReport, ImprovedResume, JobRequirements, ParsedResume
from services.llm_client import default_model_settings, get_model, json_schema_instructions, run_structured

INSTRUCTIONS = """\
You are an expert resume writer specializing in ATS optimization. You will
be given a candidate's parsed resume, the target job's requirements, and an
ATS gap analysis. Improve the resume's *wording and presentation only*.

Hard rules -- never violate these:
- NEVER invent work experience, employers, job titles, or dates that are
  not in the original resume.
- NEVER fabricate certifications, degrees, or credentials.
- NEVER claim skills the candidate has not listed or clearly demonstrated
  in their bullet points/projects. You may *recommend* missing skills
  separately (as something the candidate should consider learning/adding),
  but do not add them to the resume as if the candidate already has them.
- Only rewrite wording: strengthen verbs, add clarity, tighten phrasing,
  and naturally weave in missing ATS keywords ONLY where they truthfully
  describe what the candidate already did.

What to produce:
- improved_summary: a punchy 2-4 sentence professional summary tailored to
  this job, using the candidate's real background.
- improved_skills: the candidate's real skills list, cleaned up and
  reordered with the most job-relevant skills first.
- recommended_missing_skills: skills from the job description the
  candidate does NOT currently have, worth acquiring (clearly separate
  from improved_skills).
- recommended_keywords: ATS keywords from the job description worth
  incorporating if truthful.
- improved_experience: for each job, rewrite each bullet point using a
  strong action verb + specific detail + quantified impact where the
  original implies one; keep it truthful, do not invent numbers.
- improved_projects: same treatment for projects.
- achievements: 2-5 standout, resume-ready achievement statements drawn
  directly from the candidate's real experience/projects, phrased for
  maximum ATS + recruiter impact.
- notes: brief notes to the candidate about what changed and why.
"""

resume_improver_agent = Agent(
    name="Resume Improvement Agent",
    instructions=INSTRUCTIONS + json_schema_instructions(ImprovedResume),
    model=get_model(),
    model_settings=default_model_settings(),
)


def _build_prompt(resume: ParsedResume, jd: JobRequirements, ats_report: ATSAnalysisReport) -> str:
    payload = {
        "target_job_title": jd.job_title,
        "required_skills": jd.required_skills,
        "preferred_skills": jd.preferred_skills,
        "missing_skills": ats_report.missing_skills,
        "missing_keywords": ats_report.missing_keywords,
        "weak_bullet_points": [b.model_dump() for b in ats_report.weak_bullet_points],
        "current_summary": resume.professional_summary,
        "current_skills": resume.skills,
        "work_experience": [e.model_dump() for e in resume.work_experience],
        "projects": [p.model_dump() for p in resume.projects],
    }
    return "Candidate + job gap data (JSON):\n\n" + json.dumps(payload, indent=2)


async def improve_resume(
    resume: ParsedResume, jd: JobRequirements, ats_report: ATSAnalysisReport
) -> ImprovedResume:
    return await run_structured(
        resume_improver_agent, _build_prompt(resume, jd, ats_report), ImprovedResume
    )
