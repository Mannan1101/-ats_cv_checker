import pytest

from models.schemas import (
    ContactInfo,
    Education,
    ExperienceRequirement,
    JobRequirements,
    ParsedResume,
    Project,
    WorkExperience,
)
from services.scoring import compute_ats_score, detect_weak_bullets


@pytest.fixture
def strong_resume() -> ParsedResume:
    return ParsedResume(
        contact_info=ContactInfo(full_name="Jordan Ellis", email="jordan@email.com", phone="555-1234"),
        professional_summary="Backend engineer with 5 years of Python experience.",
        skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS", "Kubernetes"],
        work_experience=[
            WorkExperience(
                job_title="Backend Engineer",
                company="Acme Corp",
                start_date="Jan 2019",
                end_date="Present",
                is_current=True,
                bullet_points=[
                    "Reduced API latency by 35% by redesigning the caching layer",
                    "Led migration of 12 services to Kubernetes on AWS",
                ],
            )
        ],
        education=[Education(degree="B.S.", institution="UT Austin", field_of_study="Computer Science")],
        projects=[
            Project(
                name="Order Service",
                description="Order management microservice",
                technologies=["Python", "FastAPI", "Docker"],
                bullet_points=["Built a FastAPI microservice handling 1M+ requests/day"],
            )
        ],
    )


@pytest.fixture
def weak_resume() -> ParsedResume:
    return ParsedResume(
        contact_info=ContactInfo(full_name="Alex Doe"),
        skills=["Excel"],
        work_experience=[
            WorkExperience(
                job_title="Assistant",
                company="Some Co",
                bullet_points=["Responsible for helping with office tasks"],
            )
        ],
    )


@pytest.fixture
def jd() -> JobRequirements:
    return JobRequirements(
        job_title="Senior Backend Engineer",
        required_skills=["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "AWS"],
        preferred_skills=["GraphQL", "Terraform"],
        education_requirements=["Bachelor's in Computer Science or related field"],
        experience_requirement=ExperienceRequirement(minimum_years=3, level="Senior"),
        ats_keywords=["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "AWS", "microservices"],
    )


def test_strong_resume_scores_higher_than_weak_resume(strong_resume, weak_resume, jd):
    strong_score = compute_ats_score(strong_resume, jd)["ats_score"]
    weak_score = compute_ats_score(weak_resume, jd)["ats_score"]
    assert strong_score > weak_score


def test_ats_score_within_bounds(strong_resume, jd):
    data = compute_ats_score(strong_resume, jd)
    assert 0 <= data["ats_score"] <= 100
    for value in data["match_breakdown"].values():
        assert 0 <= value <= 100


def test_missing_skills_detected(weak_resume, jd):
    data = compute_ats_score(weak_resume, jd)
    assert "Python" in data["missing_skills"]
    assert "Excel" not in data["matched_skills"]  # not relevant to this JD


def test_detect_weak_bullets_flags_weak_phrases(weak_resume):
    weak_verbs, weak_bullets = detect_weak_bullets(weak_resume)
    assert "responsible for" in weak_verbs
    assert len(weak_bullets) == 1
    assert "weak phrase" in weak_bullets[0]["reason"]


def test_detect_weak_bullets_passes_strong_bullets(strong_resume):
    _, weak_bullets = detect_weak_bullets(strong_resume)
    assert weak_bullets == []


def test_no_jd_requirements_yields_full_marks_where_applicable():
    empty_jd = JobRequirements()
    resume = ParsedResume(contact_info=ContactInfo(email="a@b.com", phone="123"))
    data = compute_ats_score(resume, empty_jd)
    assert data["match_breakdown"]["keyword_match"] == 100.0
    assert data["match_breakdown"]["skills_match"] == 100.0
