"""Deterministic ATS scoring engine.

The numeric score is intentionally computed in plain Python rather than by
an LLM: it must be reproducible, auditable, and stable across runs. The ATS
Analyzer Agent calls `compute_ats_score` as a tool and then writes the
qualitative narrative (strengths/weaknesses/summary) around the numbers.

Weights (must sum to 100):
    Keyword Match   30%
    Skills Match    25%
    Experience      20%
    Projects        10%
    Education       10%
    Formatting       5%
"""

from __future__ import annotations

from models.schemas import JobRequirements, MatchBreakdown, ParsedResume
from services.keyword_matcher import (
    find_weak_verbs,
    has_quantified_result,
    match_terms,
    starts_with_strong_verb,
)

WEIGHTS = {
    "keyword_match": 0.30,
    "skills_match": 0.25,
    "experience_match": 0.20,
    "project_match": 0.10,
    "education_match": 0.10,
    "formatting_score": 0.05,
}


def _score_keywords(resume: ParsedResume, jd: JobRequirements) -> tuple[float, list[str], list[str]]:
    if not jd.ats_keywords:
        return 100.0, [], []
    result = match_terms(resume.raw_text, jd.ats_keywords)
    return result.match_ratio, result.matched, result.missing


def _score_skills(resume: ParsedResume, jd: JobRequirements) -> tuple[float, list[str], list[str]]:
    all_terms = jd.required_skills + jd.preferred_skills
    if not all_terms:
        return 100.0, [], []

    resume_haystack = resume.raw_text + " " + " ".join(resume.skills)
    required_result = match_terms(resume_haystack, jd.required_skills)
    preferred_result = match_terms(resume_haystack, jd.preferred_skills)

    # Required skills are worth more than preferred skills.
    required_weight, preferred_weight = 0.75, 0.25
    req_ratio = required_result.match_ratio if jd.required_skills else 100.0
    pref_ratio = preferred_result.match_ratio if jd.preferred_skills else 100.0
    score = req_ratio * required_weight + pref_ratio * preferred_weight

    matched = required_result.matched + preferred_result.matched
    missing = required_result.missing + preferred_result.missing
    return round(score, 2), matched, missing


def _total_years_experience(resume: ParsedResume) -> float:
    """Very rough heuristic: count non-overlapping-ish work entries * ~1.5y,
    but prefer parsed date ranges when start/end years are present."""
    import re

    total = 0.0
    for exp in resume.work_experience:
        years = None
        if exp.start_date and exp.end_date:
            start_match = re.search(r"(19|20)\d{2}", exp.start_date)
            end_text = "2026" if exp.is_current or "present" in (exp.end_date or "").lower() else exp.end_date
            end_match = re.search(r"(19|20)\d{2}", end_text or "")
            if start_match and end_match:
                years = max(0.0, float(end_match.group()) - float(start_match.group()))
        total += years if years is not None else 1.0
    return total


def _score_experience(resume: ParsedResume, jd: JobRequirements) -> float:
    required_years = jd.experience_requirement.minimum_years
    if not required_years:
        return 100.0 if resume.work_experience else 40.0
    actual_years = _total_years_experience(resume)
    if actual_years >= required_years:
        return 100.0
    if required_years == 0:
        return 100.0
    return round(max(0.0, actual_years / required_years) * 100, 2)


def _score_projects(resume: ParsedResume, jd: JobRequirements) -> float:
    relevant_terms = jd.required_skills + jd.preferred_skills
    if not resume.projects:
        return 50.0 if not relevant_terms else 0.0
    if not relevant_terms:
        return 100.0
    project_text = " ".join(
        f"{p.name} {p.description or ''} {' '.join(p.technologies)} {' '.join(p.bullet_points)}"
        for p in resume.projects
    )
    result = match_terms(project_text, relevant_terms)
    # Having *any* projects is worth a baseline; relevance boosts it further.
    baseline = 40.0
    return round(min(100.0, baseline + result.match_ratio * 0.6), 2)


def _score_education(resume: ParsedResume, jd: JobRequirements) -> float:
    if not jd.education_requirements:
        return 100.0
    if not resume.education:
        return 20.0
    resume_text = " ".join(
        f"{e.degree} {e.field_of_study or ''} {e.institution}" for e in resume.education
    )
    result = match_terms(resume_text, jd.education_requirements)
    return result.match_ratio


def _score_formatting(resume: ParsedResume) -> tuple[float, list[str]]:
    issues: list[str] = []
    score = 100.0

    if not resume.contact_info.email:
        issues.append("Missing email address in contact info")
        score -= 20
    if not resume.contact_info.phone:
        issues.append("Missing phone number in contact info")
        score -= 10
    if not resume.professional_summary:
        issues.append("Missing a professional summary section")
        score -= 15
    if resume.missing_sections:
        issues.append(f"Missing sections: {', '.join(s.value for s in resume.missing_sections)}")
        score -= 5 * len(resume.missing_sections)

    long_bullets = [
        b
        for exp in resume.work_experience
        for b in exp.bullet_points
        if len(b) > 260
    ]
    if long_bullets:
        issues.append(f"{len(long_bullets)} bullet point(s) are too long for clean ATS parsing (>260 chars)")
        score -= 5

    return max(0.0, round(score, 2)), issues


def detect_weak_bullets(resume: ParsedResume) -> tuple[list[str], list[dict]]:
    """Return (weak_action_verbs_found, weak_bullet_details)."""
    weak_verbs_found: set[str] = set()
    weak_bullets: list[dict] = []

    for exp in resume.work_experience:
        for bullet in exp.bullet_points:
            verbs = find_weak_verbs(bullet)
            weak_verbs_found.update(verbs)
            reasons = []
            if verbs:
                reasons.append(f"opens with a weak phrase ('{verbs[0]}')")
            if not starts_with_strong_verb(bullet):
                reasons.append("does not open with a strong action verb")
            if not has_quantified_result(bullet):
                reasons.append("lacks a quantified result or metric")
            if reasons:
                weak_bullets.append(
                    {
                        "original": bullet,
                        "reason": "; ".join(reasons),
                        "section": f"{exp.job_title} at {exp.company}",
                    }
                )

    return sorted(weak_verbs_found), weak_bullets


def compute_ats_score(resume: ParsedResume, jd: JobRequirements) -> dict:
    """Compute the full weighted ATS score and every supporting breakdown.

    Returns a plain dict (not a pydantic model) so it can be used directly
    as a `function_tool` return value inside the ATS Analyzer Agent.
    """
    keyword_score, matched_keywords, missing_keywords = _score_keywords(resume, jd)
    skills_score, matched_skills, missing_skills = _score_skills(resume, jd)
    experience_score = _score_experience(resume, jd)
    project_score = _score_projects(resume, jd)
    education_score = _score_education(resume, jd)
    formatting_score, formatting_issues = _score_formatting(resume)

    breakdown = MatchBreakdown(
        keyword_match=keyword_score,
        skills_match=skills_score,
        experience_match=experience_score,
        project_match=project_score,
        education_match=education_score,
        formatting_score=formatting_score,
    )

    final_score = round(
        breakdown.keyword_match * WEIGHTS["keyword_match"]
        + breakdown.skills_match * WEIGHTS["skills_match"]
        + breakdown.experience_match * WEIGHTS["experience_match"]
        + breakdown.project_match * WEIGHTS["project_match"]
        + breakdown.education_match * WEIGHTS["education_match"]
        + breakdown.formatting_score * WEIGHTS["formatting_score"],
        2,
    )

    weak_verbs, weak_bullets = detect_weak_bullets(resume)

    return {
        "ats_score": final_score,
        "match_breakdown": breakdown.model_dump(),
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "weak_action_verbs": weak_verbs,
        "weak_bullet_points": weak_bullets,
        "formatting_issues": [{"issue": i, "severity": "medium"} for i in formatting_issues],
    }
