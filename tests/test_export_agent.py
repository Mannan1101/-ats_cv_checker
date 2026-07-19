from pathlib import Path

from models.schemas import (
    ATSAnalysisReport,
    ContactInfo,
    ImprovedBullet,
    ImprovedExperience,
    ImprovedResume,
    JobRequirements,
    MatchBreakdown,
    ParsedResume,
    WorkExperience,
)
from ats_agents.export_agent import export_all


def _sample_data():
    resume = ParsedResume(
        contact_info=ContactInfo(full_name="Jordan Ellis", email="jordan@email.com"),
        professional_summary="Backend engineer.",
        skills=["Python", "FastAPI"],
        work_experience=[
            WorkExperience(job_title="Backend Engineer", company="Acme", bullet_points=["Did things"])
        ],
    )
    jd = JobRequirements(job_title="Senior Backend Engineer", company_name="Acme Corp")
    report = ATSAnalysisReport(
        ats_score=72.5,
        match_breakdown=MatchBreakdown(
            keyword_match=70, skills_match=80, experience_match=60,
            project_match=50, education_match=100, formatting_score=90,
        ),
        strengths=["Strong Python background"],
        weaknesses=["Missing Kubernetes experience"],
        summary="Solid candidate with a few gaps.",
    )
    improved = ImprovedResume(
        improved_summary="Results-driven backend engineer specializing in Python APIs.",
        improved_skills=["Python", "FastAPI"],
        recommended_missing_skills=["Kubernetes"],
        improved_experience=[
            ImprovedExperience(
                job_title="Backend Engineer",
                company="Acme",
                improved_bullets=[ImprovedBullet(original="Did things", improved="Built and shipped things")],
            )
        ],
        achievements=["Shipped a service handling 1M+ requests/day"],
    )
    return resume, jd, report, improved


def test_export_all_creates_expected_files(tmp_path: Path):
    resume, jd, report, improved = _sample_data()
    exported = export_all(resume, jd, report, improved, tmp_path)

    assert Path(exported["markdown_report"]).exists()
    assert Path(exported["pdf_report"]).exists()
    assert Path(exported["optimized_resume_docx"]).exists()

    markdown_content = Path(exported["markdown_report"]).read_text(encoding="utf-8")
    assert "72.5" in markdown_content
    assert "Strong Python background" in markdown_content
