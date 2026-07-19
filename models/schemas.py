"""Pydantic data contracts shared by every agent in the pipeline.

Each agent in ``agents/`` takes one of these models as input and returns
another as output (`Agent(output_type=...)` in the OpenAI Agents SDK), so the
coordinator can pass data between agents without ever touching raw strings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Resume Parser Agent
# --------------------------------------------------------------------------- #


class ContactInfo(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None


class Education(BaseModel):
    degree: str
    institution: str
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    gpa: str | None = None


class WorkExperience(BaseModel):
    job_title: str
    company: str
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None
    bullet_points: list[str] = Field(default_factory=list)
    is_current: bool = False


class Project(BaseModel):
    name: str
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    bullet_points: list[str] = Field(default_factory=list)
    link: str | None = None


class Certification(BaseModel):
    name: str
    issuer: str | None = None
    date: str | None = None


class ResumeSection(str, Enum):
    CONTACT = "contact"
    SUMMARY = "summary"
    SKILLS = "skills"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    PROJECTS = "projects"
    CERTIFICATIONS = "certifications"


class ParsedResume(BaseModel):
    """Structured output of the Resume Parser Agent."""

    contact_info: ContactInfo = Field(default_factory=ContactInfo)
    professional_summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    work_experience: list[WorkExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    missing_sections: list[ResumeSection] = Field(default_factory=list)
    raw_text: str = Field(default="", repr=False)


# --------------------------------------------------------------------------- #
# Job Description Analyzer Agent
# --------------------------------------------------------------------------- #


class ExperienceRequirement(BaseModel):
    minimum_years: float | None = None
    level: str | None = None  # e.g. "Entry", "Mid", "Senior", "Lead"


class JobRequirements(BaseModel):
    """Structured output of the Job Description Analyzer Agent."""

    job_title: str | None = None
    company_name: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    experience_requirement: ExperienceRequirement = Field(default_factory=ExperienceRequirement)
    education_requirements: list[str] = Field(default_factory=list)
    ats_keywords: list[str] = Field(default_factory=list)
    raw_text: str = Field(default="", repr=False)


# --------------------------------------------------------------------------- #
# ATS Analyzer Agent
# --------------------------------------------------------------------------- #


class MatchBreakdown(BaseModel):
    keyword_match: float = Field(ge=0, le=100)
    skills_match: float = Field(ge=0, le=100)
    experience_match: float = Field(ge=0, le=100)
    project_match: float = Field(ge=0, le=100)
    education_match: float = Field(ge=0, le=100)
    formatting_score: float = Field(ge=0, le=100)


class WeakBulletPoint(BaseModel):
    original: str
    reason: str
    section: str | None = None


class FormattingIssue(BaseModel):
    issue: str
    severity: str = "medium"  # low | medium | high


class ATSAnalysisReport(BaseModel):
    """Structured output of the ATS Analyzer Agent."""

    ats_score: float = Field(ge=0, le=100)
    match_breakdown: MatchBreakdown
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    weak_bullet_points: list[WeakBulletPoint] = Field(default_factory=list)
    weak_action_verbs: list[str] = Field(default_factory=list)
    formatting_issues: list[FormattingIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    summary: str | None = None


# --------------------------------------------------------------------------- #
# Resume Improvement Agent
# --------------------------------------------------------------------------- #


class ImprovedBullet(BaseModel):
    original: str
    improved: str
    reason: str | None = None


class ImprovedExperience(BaseModel):
    job_title: str
    company: str
    improved_bullets: list[ImprovedBullet] = Field(default_factory=list)


class ImprovedProject(BaseModel):
    name: str
    improved_bullets: list[ImprovedBullet] = Field(default_factory=list)


class ImprovedResume(BaseModel):
    """Structured output of the Resume Improvement Agent."""

    improved_summary: str
    improved_skills: list[str] = Field(default_factory=list)
    recommended_missing_skills: list[str] = Field(default_factory=list)
    recommended_keywords: list[str] = Field(default_factory=list)
    improved_experience: list[ImprovedExperience] = Field(default_factory=list)
    improved_projects: list[ImprovedProject] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    notes: str | None = None


# --------------------------------------------------------------------------- #
# Cover Letter Agent
# --------------------------------------------------------------------------- #


class CoverLetterRequest(BaseModel):
    company_name: str
    job_title: str
    hiring_manager: str | None = None


class CoverLetter(BaseModel):
    """Structured output of the Cover Letter Agent."""

    greeting: str
    opening_paragraph: str
    body_paragraphs: list[str] = Field(default_factory=list)
    closing_paragraph: str
    signature: str
    full_text: str


# --------------------------------------------------------------------------- #
# Pipeline / Database
# --------------------------------------------------------------------------- #


class PipelineResult(BaseModel):
    """Everything produced by one end-to-end coordinator run."""

    parsed_resume: ParsedResume
    job_requirements: JobRequirements
    ats_report: ATSAnalysisReport
    improved_resume: ImprovedResume
    cover_letter: CoverLetter | None = None
    exported_files: dict[str, str] = Field(default_factory=dict)
    record_id: int | None = None


class AnalysisRecord(BaseModel):
    """Row shape returned from the Database Agent / history endpoints."""

    id: int | None = None
    candidate_name: str | None = None
    job_title: str | None = None
    company_name: str | None = None
    ats_score: float
    resume_path: str | None = None
    jd_path: str | None = None
    report_path: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
