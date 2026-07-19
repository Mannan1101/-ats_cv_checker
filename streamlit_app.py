"""ATS CV Checker & Optimizer -- Streamlit dashboard.

A thin UI layer over the exact same pipeline the CLI (`main.py`) and API
(`api.py`) use (`ats_agents.coordinator.run_pipeline`) -- no business logic
is duplicated here, only presentation.

Run with:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from ats_agents import database_agent
from ats_agents.coordinator import run_pipeline
from models.schemas import ATSAnalysisReport, MatchBreakdown, PipelineResult
from services.database import init_db

load_dotenv()

st.set_page_config(
    page_title="ATS CV Checker & Optimizer",
    page_icon="\U0001F4C4",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Styling
# --------------------------------------------------------------------------- #

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; max-width: 1200px; }

    .hero {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 55%, #a855f7 100%);
        border-radius: 18px;
        padding: 2rem 2.25rem;
        margin-bottom: 1.75rem;
        box-shadow: 0 10px 30px -12px rgba(79, 70, 229, 0.55);
    }
    .hero h1 { color: white; margin: 0 0 0.35rem 0; font-size: 2rem; }
    .hero p { color: #e9e5ff; margin: 0; font-size: 1.02rem; }

    .card {
        background: rgba(148, 163, 184, 0.06);
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 14px;
        padding: 1.25rem 1.4rem;
        margin-bottom: 1rem;
    }
    .card h4 { margin-top: 0; }

    .chip {
        display: inline-block;
        padding: 0.28rem 0.75rem;
        border-radius: 999px;
        font-size: 0.85rem;
        margin: 0.2rem 0.3rem 0.2rem 0;
        font-weight: 500;
    }
    .chip-good { background: rgba(34, 197, 94, 0.16); color: #4ade80; border: 1px solid rgba(34,197,94,0.35); }
    .chip-bad { background: rgba(239, 68, 68, 0.14); color: #f87171; border: 1px solid rgba(239,68,68,0.32); }

    .bullet-diff {
        border-left: 3px solid #6366f1;
        padding: 0.5rem 0 0.5rem 0.9rem;
        margin-bottom: 0.65rem;
        background: rgba(99, 102, 241, 0.05);
        border-radius: 0 8px 8px 0;
    }
    .bullet-diff .orig { color: #94a3b8; text-decoration: line-through; font-size: 0.9rem; }
    .bullet-diff .improved { color: #e2e8f0; font-size: 0.96rem; }

    .empty-state {
        text-align: center;
        padding: 3.5rem 1rem;
        color: #94a3b8;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def run_async(coro):
    return asyncio.run(coro)
run_async(init_db())

def save_uploaded_file(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".txt"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded_file.getvalue())
    tmp.close()
    return Path(tmp.name)


def score_color(score: float) -> str:
    if score >= 75:
        return "#22c55e"
    if score >= 50:
        return "#eab308"
    return "#ef4444"


def score_gauge(score: float) -> go.Figure:
    color = score_color(score)
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": " / 100", "font": {"size": 36, "color": "#e2e8f0"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#64748b"},
                "bar": {"color": color, "thickness": 0.28},
                "bgcolor": "rgba(0,0,0,0)",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 50], "color": "rgba(239, 68, 68, 0.12)"},
                    {"range": [50, 75], "color": "rgba(234, 179, 8, 0.12)"},
                    {"range": [75, 100], "color": "rgba(34, 197, 94, 0.12)"},
                ],
            },
        )
    )
    fig.update_layout(
        height=260,
        margin=dict(l=20, r=20, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e2e8f0"},
    )
    return fig


def breakdown_chart(breakdown: MatchBreakdown) -> go.Figure:
    labels = [
        "Keyword Match (30%)", "Skills Match (25%)", "Experience (20%)",
        "Projects (10%)", "Education (10%)", "Formatting (5%)",
    ]
    values = [
        breakdown.keyword_match, breakdown.skills_match, breakdown.experience_match,
        breakdown.project_match, breakdown.education_match, breakdown.formatting_score,
    ]
    colors = [score_color(v) for v in values]
    fig = go.Figure(
        go.Bar(
            x=values, y=labels, orientation="h",
            marker=dict(color=colors), text=[f"{v}%" for v in values],
            textposition="outside",
        )
    )
    fig.update_layout(
        height=280,
        margin=dict(l=10, r=40, t=10, b=10),
        xaxis=dict(range=[0, 105], showgrid=False, visible=False),
        yaxis=dict(autorange="reversed"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e2e8f0"},
    )
    return fig


def chips(items: list[str], kind: str) -> str:
    css_class = "chip-good" if kind == "good" else "chip-bad"
    if not items:
        return "<span style='color:#64748b;'>None</span>"
    return "".join(f"<span class='chip {css_class}'>{i}</span>" for i in items)


def mime_for(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".md": "text/markdown",
    }.get(ext, "application/octet-stream")


# --------------------------------------------------------------------------- #
# Sidebar -- inputs
# --------------------------------------------------------------------------- #

with st.sidebar:
    st.markdown("### \U0001F4C4 ATS CV Checker")
    st.caption("Multi-agent resume analysis, powered by the OpenAI Agents SDK")
    st.divider()

    resume_file = st.file_uploader("Resume", type=["pdf", "docx", "txt"])

    jd_mode = st.radio("Job Description", ["Paste text", "Upload file"], horizontal=True)
    jd_text, jd_file = None, None
    if jd_mode == "Paste text":
        jd_text = st.text_area("Job description text", height=180, placeholder="Paste the job description here...")
    else:
        jd_file = st.file_uploader("Job description file", type=["txt", "md"], key="jd_file")

    company_name = st.text_input("Company name (optional)")
    job_title = st.text_input("Job title (optional)")
    hiring_manager = st.text_input("Hiring manager (optional)")
    generate_cover_letter = st.checkbox("Generate cover letter", value=True)

    st.divider()
    analyze_clicked = st.button("\U0001F680 Analyze Resume", type="primary", width="stretch")

# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #

st.markdown(
    """
    <div class="hero">
        <h1>ATS CV Checker &amp; Optimizer</h1>
        <p>Score your resume against any job description, see exactly what's missing,
        and get an ATS-optimized rewrite -- in one pass.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if "result" not in st.session_state:
    st.session_state.result = None

# --------------------------------------------------------------------------- #
# Analyze action
# --------------------------------------------------------------------------- #

if analyze_clicked:
    if resume_file is None:
        st.error("Please upload a resume file.")
    elif jd_mode == "Paste text" and not (jd_text or "").strip():
        st.error("Please paste a job description, or switch to file upload.")
    elif jd_mode == "Upload file" and jd_file is None:
        st.error("Please upload a job description file.")
    else:
        resume_path = save_uploaded_file(resume_file)
        jd_input = jd_text if jd_mode == "Paste text" else str(save_uploaded_file(jd_file))
        try:
            with st.spinner("Running the multi-agent pipeline... this can take 30-90 seconds."):
                result: PipelineResult = run_async(
                    run_pipeline(
                        resume_path=resume_path,
                        jd_text_or_path=jd_input,
                        output_dir="exports",
                        company_name=company_name or None,
                        job_title=job_title or None,
                        hiring_manager=hiring_manager or None,
                        generate_cover_letter_flag=generate_cover_letter,
                    )
                )
            st.session_state.result = result
            st.success(f"Analysis complete -- saved as record #{result.record_id}")
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Pipeline failed: {exc}")
        finally:
            resume_path.unlink(missing_ok=True)

# --------------------------------------------------------------------------- #
# Main tabs
# --------------------------------------------------------------------------- #

tab_analyze, tab_history = st.tabs(["\U0001F50D Results", "\U0001F553 History"])

with tab_analyze:
    result: PipelineResult | None = st.session_state.result

    if result is None:
        st.markdown(
            """
            <div class="empty-state">
                <h3>No analysis yet</h3>
                <p>Upload a resume and a job description in the sidebar, then click
                <b>Analyze Resume</b> to get your ATS score, gap analysis, and an
                optimized rewrite.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        report: ATSAnalysisReport = result.ats_report
        resume = result.parsed_resume
        improved = result.improved_resume

        col_gauge, col_summary = st.columns([1, 2])
        with col_gauge:
            st.plotly_chart(score_gauge(report.ats_score), width="stretch")
        with col_summary:
            st.markdown(
                f"""<div class="card"><h4>Executive Summary</h4><p>{report.summary or ""}</p></div>""",
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            c1.metric("Candidate", resume.contact_info.full_name or "N/A")
            c2.metric("Target Role", result.job_requirements.job_title or "N/A")

        sub1, sub2, sub3, sub4 = st.tabs(
            ["\U0001F4CA Breakdown", "\U0001F3AF Gaps", "✨ Improvements", "\U0001F4E5 Exports"]
        )

        with sub1:
            st.plotly_chart(breakdown_chart(report.match_breakdown), width="stretch")
            col_s, col_w = st.columns(2)
            with col_s:
                st.markdown("**Strengths**")
                for s in report.strengths:
                    st.markdown(f"- {s}")
            with col_w:
                st.markdown("**Weaknesses**")
                for w in report.weaknesses:
                    st.markdown(f"- {w}")

        with sub2:
            st.markdown("**Matched keywords**")
            st.markdown(chips(report.matched_keywords, "good"), unsafe_allow_html=True)
            st.markdown("**Missing keywords**")
            st.markdown(chips(report.missing_keywords, "bad"), unsafe_allow_html=True)
            st.markdown("**Matched skills**")
            st.markdown(chips(report.matched_skills, "good"), unsafe_allow_html=True)
            st.markdown("**Missing skills**")
            st.markdown(chips(report.missing_skills, "bad"), unsafe_allow_html=True)

            if report.weak_bullet_points:
                st.markdown("**Weak bullet points**")
                for b in report.weak_bullet_points:
                    st.markdown(
                        f"""<div class="card"><span class="orig">{b.original}</span><br>
                        <span style="color:#94a3b8;font-size:0.85rem;">{b.reason}</span></div>""",
                        unsafe_allow_html=True,
                    )

        with sub3:
            st.markdown(f"""<div class="card"><h4>Improved Summary</h4><p>{improved.improved_summary}</p></div>""", unsafe_allow_html=True)

            if improved.recommended_missing_skills:
                st.markdown("**Recommended skills to add**")
                st.markdown(chips(improved.recommended_missing_skills, "bad"), unsafe_allow_html=True)

            for exp in improved.improved_experience:
                st.markdown(f"**{exp.job_title} at {exp.company}**")
                for b in exp.improved_bullets:
                    st.markdown(
                        f"""<div class="bullet-diff">
                        <div class="orig">{b.original}</div>
                        <div class="improved">→ {b.improved}</div>
                        </div>""",
                        unsafe_allow_html=True,
                    )

            if improved.achievements:
                st.markdown("**Key achievements**")
                for a in improved.achievements:
                    st.markdown(f"- {a}")

            if result.cover_letter:
                with st.expander("\U0001F4E8 Cover Letter", expanded=False):
                    st.markdown(result.cover_letter.full_text)

        with sub4:
            st.markdown("Download the generated files:")
            cols = st.columns(len(result.exported_files) or 1)
            for col, (kind, path) in zip(cols, result.exported_files.items()):
                p = Path(path)
                if p.exists():
                    col.download_button(
                        label=kind.replace("_", " ").title(),
                        data=p.read_bytes(),
                        file_name=p.name,
                        mime=mime_for(path),
                        width="stretch",
                    )

with tab_history:
    st.markdown("### Past Analyses")
    search = st.text_input("Search by candidate, job title, or company", key="history_search")
    records = run_async(database_agent.get_history(limit=50, search=search or None))

    if not records:
        st.info("No analyses saved yet.")
    else:
        st.dataframe(
            [
                {
                    "ID": r.id,
                    "Candidate": r.candidate_name,
                    "Job Title": r.job_title,
                    "Company": r.company_name,
                    "ATS Score": r.ats_score,
                    "Date": r.created_at.strftime("%Y-%m-%d %H:%M"),
                }
                for r in records
            ],
            width="stretch",
            hide_index=True,
        )
