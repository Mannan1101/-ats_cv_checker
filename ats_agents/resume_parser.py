"""Resume Parser Agent.

Reads a PDF/DOCX/TXT resume, extracts raw text deterministically (no LLM
needed for that part), then asks the LLM to structure it into a
`ParsedResume`. Missing-section detection is re-verified in plain Python
afterwards so it doesn't depend on the model noticing correctly.
"""

from __future__ import annotations

from pathlib import Path

from agents import Agent

from models.schemas import ParsedResume, ResumeSection
from services.docx_reader import read_resume_text
from services.llm_client import default_model_settings, get_model, json_schema_instructions, run_structured

INSTRUCTIONS = """\
You are an expert resume parser used by an ATS (Applicant Tracking System).

You will be given the raw extracted text of a candidate's resume. Extract a
complete, structured representation of it:

- Contact info (name, email, phone, location, LinkedIn, GitHub, portfolio)
- Professional summary (verbatim if present, otherwise leave null)
- Skills as a flat list of individual skill strings
- Work experience: job title, company, dates, location, bullet points
  (split each bullet into its own list item, preserve original wording)
- Education: degree, institution, field of study, dates, GPA if present
- Projects: name, description, technologies used, bullet points
- Certifications: name, issuer, date

Rules:
- Never invent information that is not present in the text.
- If a field is not present, leave it null or an empty list.
- Preserve the candidate's original wording for bullet points and summary;
  do not rewrite or improve anything at this stage, you are only extracting.
- Detect which of these standard sections appear to be entirely absent from
  the resume: contact, summary, skills, experience, education, projects,
  certifications. Populate `missing_sections` with those.
"""

resume_parser_agent = Agent(
    name="Resume Parser Agent",
    instructions=INSTRUCTIONS + json_schema_instructions(ParsedResume),
    model=get_model(),
    model_settings=default_model_settings(),
)


def _reconcile_missing_sections(parsed: ParsedResume) -> ParsedResume:
    """Deterministic safety net on top of the LLM's own judgement."""
    missing: set[ResumeSection] = set(parsed.missing_sections)

    if not (parsed.contact_info.email or parsed.contact_info.phone):
        missing.add(ResumeSection.CONTACT)
    if not parsed.professional_summary:
        missing.add(ResumeSection.SUMMARY)
    if not parsed.skills:
        missing.add(ResumeSection.SKILLS)
    if not parsed.work_experience:
        missing.add(ResumeSection.EXPERIENCE)
    if not parsed.education:
        missing.add(ResumeSection.EDUCATION)
    if not parsed.projects:
        missing.add(ResumeSection.PROJECTS)
    if not parsed.certifications:
        missing.add(ResumeSection.CERTIFICATIONS)

    parsed.missing_sections = sorted(missing, key=lambda s: s.value)
    return parsed


async def parse_resume(file_path: str | Path) -> ParsedResume:
    """Extract text from the resume file and structure it via the LLM."""
    raw_text = read_resume_text(file_path)
    if not raw_text.strip():
        raise ValueError(f"No extractable text found in resume: {file_path}")

    parsed = await run_structured(
        resume_parser_agent,
        f"Resume text extracted from '{Path(file_path).name}':\n\n{raw_text}",
        ParsedResume,
    )
    parsed.raw_text = raw_text
    return _reconcile_missing_sections(parsed)
