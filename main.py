"""ATS CV Checker & Optimizer -- CLI entry point (Typer + Rich)."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    # Windows terminals default to the cp1252 codepage, which can't encode
    # many characters LLMs commonly produce (em dashes, curly quotes, non-
    # breaking hyphens). Force UTF-8 so Rich output never crashes on them.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

app = typer.Typer(help="ATS CV Checker & Optimizer -- multi-agent resume analysis.")
console = Console()


@app.command()
def analyze(
    resume: str | None = typer.Option(None, "--resume", "-r", help="Path to resume (PDF/DOCX/TXT)."),
    jd: str | None = typer.Option(None, "--jd", "-j", help="Path to job description file, or raw JD text."),
    output: str | None = typer.Option(None, "--output", "-o", help="Output folder for reports."),
    company: str | None = typer.Option(None, "--company", help="Company name (for cover letter)."),
    job_title: str | None = typer.Option(None, "--job-title", help="Job title (for cover letter)."),
    hiring_manager: str | None = typer.Option(None, "--hiring-manager", help="Hiring manager name (optional)."),
    no_cover_letter: bool = typer.Option(False, "--no-cover-letter", help="Skip cover letter generation."),
) -> None:
    """Run the full ATS analysis + optimization pipeline on a resume + JD."""
    console.print(Panel.fit("ATS CV Checker & Optimizer", style="bold cyan"))

    resume = resume or Prompt.ask("Resume path (PDF/DOCX/TXT)")
    jd = jd or Prompt.ask("Job description path (or paste JD text)")
    output = output or Prompt.ask("Output folder", default="reports")

    if not Path(resume).exists():
        console.print(f"[bold red]Resume file not found:[/bold red] {resume}")
        raise typer.Exit(code=1)

    with console.status("[bold green]Running multi-agent pipeline..."):
        result = asyncio.run(
            _run(
                resume_path=resume,
                jd_text_or_path=jd,
                output_dir=output,
                company_name=company,
                job_title=job_title,
                hiring_manager=hiring_manager,
                generate_cover_letter_flag=not no_cover_letter,
            )
        )

    _render_result(result)


async def _run(**kwargs):
    from ats_agents.coordinator import run_pipeline

    return await run_pipeline(**kwargs)


def _render_result(result) -> None:
    report = result.ats_report

    table = Table(title=f"ATS Score: {report.ats_score}/100", show_header=True, header_style="bold magenta")
    table.add_column("Category")
    table.add_column("Score", justify="right")
    breakdown = report.match_breakdown
    table.add_row("Keyword Match (30%)", f"{breakdown.keyword_match}%")
    table.add_row("Skills Match (25%)", f"{breakdown.skills_match}%")
    table.add_row("Experience Match (20%)", f"{breakdown.experience_match}%")
    table.add_row("Project Match (10%)", f"{breakdown.project_match}%")
    table.add_row("Education Match (10%)", f"{breakdown.education_match}%")
    table.add_row("Formatting (5%)", f"{breakdown.formatting_score}%")
    console.print(table)

    console.print(Panel(report.summary or "", title="Executive Summary", style="cyan"))

    if report.missing_keywords:
        console.print(f"[yellow]Missing keywords:[/yellow] {', '.join(report.missing_keywords)}")
    if report.missing_skills:
        console.print(f"[yellow]Missing skills:[/yellow] {', '.join(report.missing_skills)}")

    console.print("\n[bold]Exported files:[/bold]")
    for kind, path in result.exported_files.items():
        console.print(f"  - {kind}: {path}")

    if result.record_id is not None:
        console.print(f"\n[green]Saved to database as record #{result.record_id}[/green]")


@app.command()
def history(
    search: str | None = typer.Option(None, "--search", "-s", help="Search by name/job title/company."),
    limit: int = typer.Option(20, "--limit", "-n", help="Max records to show."),
) -> None:
    """Show past analysis runs stored in the local SQLite database."""

    async def _get():
        from ats_agents import database_agent

        await database_agent.initialize()
        return await database_agent.get_history(limit=limit, search=search)

    records = asyncio.run(_get())
    if not records:
        console.print("[yellow]No history found.[/yellow]")
        raise typer.Exit()

    table = Table(title="Analysis History", header_style="bold magenta")
    table.add_column("ID")
    table.add_column("Candidate")
    table.add_column("Job Title")
    table.add_column("Company")
    table.add_column("ATS Score")
    table.add_column("Date")
    for r in records:
        table.add_row(
            str(r.id), r.candidate_name or "-", r.job_title or "-",
            r.company_name or "-", f"{r.ats_score}", r.created_at.strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)


if __name__ == "__main__":
    app()
