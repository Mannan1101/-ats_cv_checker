"""ATS Analyzer Agent.

The *numbers* (ATS score, match breakdown, matched/missing keywords &
skills, weak bullets, formatting issues) are computed deterministically by
`services.scoring` -- they must be reproducible and auditable, not subject
to LLM variance. The LLM's job here is narrower and better suited to it:
write the qualitative strengths/weaknesses narrative and a short executive
summary, grounded in those computed numbers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents import Agent

from models.schemas import ATSAnalysisReport, JobRequirements, ParsedResume
from services.llm_client import default_model_settings, get_model, json_schema_instructions, run_structured
from services.scoring import compute_ats_score

INSTRUCTIONS = """\
You are a senior ATS (Applicant Tracking System) analyst. You are given the
already-computed match statistics between a candidate's resume and a job
description. Do not recompute or second-guess the numbers -- treat them as
ground truth.

Your job is to:
- List 3-6 genuine strengths of this resume relative to this specific job.
- List 3-6 concrete weaknesses relative to this specific job.
- Write a 2-4 sentence executive summary of the candidate's fit, referencing
  the ATS score and the most important gaps.

Be specific and reference actual skills/keywords from the data given, not
generic advice.
"""


class _QualitativeInsights(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    summary: str


ats_analyzer_agent = Agent(
    name="ATS Analyzer Agent",
    instructions=INSTRUCTIONS + json_schema_instructions(_QualitativeInsights),
    model=get_model(),
    model_settings=default_model_settings(),
)


def _build_stats_prompt(resume: ParsedResume, jd: JobRequirements, score_data: dict) -> str:
    return f"""\
Job title: {jd.job_title or "N/A"}
Candidate current role: {resume.work_experience[0].job_title if resume.work_experience else "N/A"}

ATS Score: {score_data['ats_score']}/100

Match breakdown:
- Keyword match: {score_data['match_breakdown']['keyword_match']}%
- Skills match: {score_data['match_breakdown']['skills_match']}%
- Experience match: {score_data['match_breakdown']['experience_match']}%
- Project match: {score_data['match_breakdown']['project_match']}%
- Education match: {score_data['match_breakdown']['education_match']}%
- Formatting score: {score_data['match_breakdown']['formatting_score']}%

Matched skills: {', '.join(score_data['matched_skills']) or 'none'}
Missing skills: {', '.join(score_data['missing_skills']) or 'none'}
Matched keywords: {', '.join(score_data['matched_keywords'][:20]) or 'none'}
Missing keywords: {', '.join(score_data['missing_keywords']) or 'none'}
Weak action verbs found: {', '.join(score_data['weak_action_verbs']) or 'none'}
Number of weak bullet points: {len(score_data['weak_bullet_points'])}
Formatting issues: {'; '.join(i['issue'] for i in score_data['formatting_issues']) or 'none'}
"""


async def analyze_ats_fit(resume: ParsedResume, jd: JobRequirements) -> ATSAnalysisReport:
    score_data = compute_ats_score(resume, jd)

    insights = await run_structured(
        ats_analyzer_agent, _build_stats_prompt(resume, jd, score_data), _QualitativeInsights
    )

    return ATSAnalysisReport(
        ats_score=score_data["ats_score"],
        match_breakdown=score_data["match_breakdown"],
        matched_keywords=score_data["matched_keywords"],
        missing_keywords=score_data["missing_keywords"],
        matched_skills=score_data["matched_skills"],
        missing_skills=score_data["missing_skills"],
        weak_bullet_points=score_data["weak_bullet_points"],
        weak_action_verbs=score_data["weak_action_verbs"],
        formatting_issues=score_data["formatting_issues"],
        strengths=insights.strengths,
        weaknesses=insights.weaknesses,
        summary=insights.summary,
    )
