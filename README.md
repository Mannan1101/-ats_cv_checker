# ATS CV Checker & Optimizer

A multi-agent ATS (Applicant Tracking System) resume checker built on the
**OpenAI Agents SDK**. Upload a resume + a job description and get: an ATS
compatibility score, a full gap analysis, an ATS-optimized resume, and a
tailored cover letter — via a Streamlit dashboard, a CLI, or a FastAPI
service.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design
rationale and a diagram.

## How it works

Seven specialized agents, run in a fixed pipeline by a plain-Python
**Coordinator**:

1. **Resume Parser Agent** — PDF/DOCX/TXT → structured resume data
2. **Job Description Analyzer Agent** — JD text → structured requirements
3. **ATS Analyzer Agent** — deterministic scoring engine + LLM narrative
4. **Resume Improvement Agent** — rewrites wording, never fabricates experience
5. **Cover Letter Agent** — tailored cover letter from real resume data
6. **Export Agent** — Markdown report, PDF report, optimized DOCX resume, DOCX cover letter
7. **Database Agent** — SQLite history, searchable

## Model provider: OpenRouter

This project talks to an OpenAI-compatible endpoint (OpenRouter) instead of
OpenAI directly — configured entirely through `.env`, no code changes
needed to switch providers/models. See `services/llm_client.py`.

The default model (`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`) is
free-tier but reliably fast in practice — a full 6-step pipeline run
typically completes in ~60-90 seconds with no retries needed. Free-tier
models can still occasionally be flaky (dropped connections, malformed
JSON), so `services/llm_client.run_structured()` automatically retries on
those, up to 3 attempts, feeding the exact error back to the model.

Swap `OPENROUTER_MODEL_NAME` in `.env` for any other OpenRouter model
(free or paid) with no code changes required.

## Installation

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# then edit .env and set OPENROUTER_API_KEY
```

## Usage

### Streamlit dashboard (recommended)

```bash
streamlit run streamlit_app.py
```

Opens at `http://localhost:8501`. Upload a resume, paste (or upload) a job
description, optionally add company/job title/hiring manager, and click
**Analyze Resume**. Results are shown across four tabs — score breakdown
(gauge + bar chart), keyword/skill gaps, side-by-side bullet-point
improvements, and one-click downloads for every exported file — plus a
searchable **History** tab backed by the same SQLite database as the CLI.
The dashboard calls `ats_agents.coordinator.run_pipeline` directly, so it
stays in sync with the CLI/API automatically.

### CLI

```bash
# Interactive prompts:
python main.py analyze

# Or fully via flags:
python main.py analyze \
  --resume examples/example_resume.txt \
  --jd examples/example_job_description.txt \
  --company "Meridian Cloud Technologies" \
  --job-title "Senior Backend Engineer" \
  --output reports

# View past analyses:
python main.py history
python main.py history --search "Meridian"
```

Output: an ATS score table in the terminal, plus exported files in
`--output` (Markdown report, PDF report, optimized DOCX resume, and a DOCX
cover letter if company/job title were provided).

### API

```bash
uvicorn api:app --reload
```

Then see interactive docs at `http://127.0.0.1:8000/docs`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/analyze` | Full pipeline: parse → score → improve → (cover letter) → export → save |
| POST | `/improve` | Parse + score + improve only (no export/db/cover letter) |
| POST | `/cover-letter` | Generate a cover letter from a resume + job/company info |
| GET | `/history` | List past analyses (`?search=`, `?limit=`) |
| GET | `/report/{id}` | Fetch one stored analysis by id |
| GET | `/health` | Liveness check |

Example:

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -F "resume=@examples/example_resume.txt" \
  -F "job_description=$(cat examples/example_job_description.txt)" \
  -F "company_name=Meridian Cloud Technologies" \
  -F "job_title=Senior Backend Engineer"
```

## Testing

```bash
pytest
```

Tests cover the deterministic parts of the system (scoring engine, keyword
matching, file readers, export rendering) — the parts that must be
reproducible and don't require a live model call. They run offline and
don't hit the OpenRouter API.

## Project structure

```
project/
  ats_agents/            # one module per agent (see docs/ARCHITECTURE.md
    resume_parser.py     #  for why this isn't named `agents/`)
    jd_analyzer.py
    ats_analyzer.py
    resume_improver.py
    cover_letter.py
    export_agent.py
    database_agent.py
    coordinator.py
  models/
    schemas.py           # every cross-agent Pydantic data contract
  services/
    pdf_reader.py
    docx_reader.py
    keyword_matcher.py
    scoring.py            # deterministic ATS scoring engine
    database.py            # SQLite (aiosqlite)
    llm_client.py           # OpenRouter wiring + resilient structured-output parsing
  templates/
    report_template.md.j2
  tests/
  examples/
    example_resume.txt
    example_job_description.txt
    example_output/        # sample generated report/resume/cover-letter from a real run
  reports/                # default CLI output folder
  exports/                # default API/Streamlit output folder
  data/                   # SQLite database file
  main.py                 # Typer CLI
  api.py                  # FastAPI service
  streamlit_app.py        # Streamlit dashboard
  requirements.txt
  .env.example
```

## Design notes / deviations from a literal read of the spec

- **`ats_agents/` instead of `agents/`** — the OpenAI Agents SDK package
  itself is `import agents`; a same-named local package would shadow it.
- **DOCX/PDF templates generated in code, not stored as binary template
  files** — `ats_agents/export_agent.py` builds the DOCX/PDF documents
  directly with `python-docx`/`reportlab`, which is easier to keep in sync
  with the data model than a static `.docx` template with merge fields.
- **ATS score is deterministic Python, not an LLM call** — see
  `docs/ARCHITECTURE.md` for why.
- **Coordinator is a fixed async pipeline, not LLM-driven handoffs** —
  the six steps are not a routing decision.

## Truthfulness guarantees

The Resume Improvement Agent and Cover Letter Agent are explicitly
instructed to never invent work experience, employers, dates, degrees, or
certifications — they only rewrite wording and may *recommend* (separately)
skills the candidate doesn't have yet.
