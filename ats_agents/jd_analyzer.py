"""Job Description Analyzer Agent.

Turns a raw job description (plain text, pasted or read from a file) into a
structured `JobRequirements` model the ATS Analyzer Agent can compare a
resume against.
"""

from __future__ import annotations

from pathlib import Path

from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrail,
    InputGuardrailTripwireTriggered,
    RunContextWrapper,
)

from models.schemas import JobRequirements
from services.llm_client import default_model_settings, get_model, json_schema_instructions, run_structured

_MIN_JD_LENGTH = 50


async def _jd_length_guardrail(
    ctx: RunContextWrapper, agent: Agent, agent_input: str | list
) -> GuardrailFunctionOutput:
    """Reject obviously-too-short input before spending a model call on it."""
    text = agent_input if isinstance(agent_input, str) else str(agent_input)
    length = len(text.strip())
    return GuardrailFunctionOutput(
        output_info={"length": length, "minimum_required": _MIN_JD_LENGTH},
        tripwire_triggered=length < _MIN_JD_LENGTH,
    )

INSTRUCTIONS = """\
You are an expert technical recruiter analyzing a job description (JD) to
prepare it for automated resume screening.

From the JD text, extract:

- job_title and company_name if stated
- required_skills: skills/technologies explicitly required ("must have",
  "required", listed under a "Requirements" heading, etc.)
- preferred_skills: skills described as a plus / nice-to-have / preferred
- responsibilities: the core day-to-day responsibilities, as short phrases
- experience_requirement: minimum_years (a number, or null) and a level
  such as "Entry", "Mid", "Senior", "Lead", "Staff", inferred from the text
- education_requirements: degree/field requirements (e.g. "Bachelor's in
  Computer Science or related field")
- ats_keywords: the important keywords/phrases a real ATS system would
  scan for -- include tools, frameworks, methodologies, certifications,
  and domain terms mentioned anywhere in the JD (this list may overlap
  with required/preferred skills, that's fine)

Be exhaustive but do not invent requirements that are not implied by the
text.
"""

jd_analyzer_agent = Agent(
    name="Job Description Analyzer Agent",
    instructions=INSTRUCTIONS + json_schema_instructions(JobRequirements),
    model=get_model(),
    model_settings=default_model_settings(),
    input_guardrails=[InputGuardrail(guardrail_function=_jd_length_guardrail)],
)


async def analyze_job_description(text_or_path: str) -> JobRequirements:
    """Accepts either raw JD text or a path to a .txt/.md file containing it."""
    candidate_path = Path(text_or_path)
    if candidate_path.suffix.lower() in (".txt", ".md") and candidate_path.exists():
        jd_text = candidate_path.read_text(encoding="utf-8")
    else:
        jd_text = text_or_path

    if not jd_text.strip():
        raise ValueError("Job description text is empty")

    try:
        requirements = await run_structured(
            jd_analyzer_agent, f"Job description:\n\n{jd_text}", JobRequirements
        )
    except InputGuardrailTripwireTriggered as exc:
        raise ValueError(
            f"Job description is too short to analyze (minimum {_MIN_JD_LENGTH} characters)."
        ) from exc

    requirements.raw_text = jd_text
    return requirements
