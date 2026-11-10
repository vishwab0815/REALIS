"""Command-line entry point: `realis analyze photo.jpg | call.m4a | clip.mp4`."""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from realis import DISPLAY_NAME, FULL_NAME, TAGLINE, settings
from realis.core.analyzer import analyzers_for
from realis.core.custody import CaseStore, sha256_file
from realis.core.fusion import top_finding
from realis.core.models import Severity, Status
from realis.ml import antideepfake, trufor
from realis.pipeline import analyze_media

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  help=f"{DISPLAY_NAME}: {FULL_NAME}. {TAGLINE}")
console = Console()

_SEV_STYLE = {Severity.INFO: "dim", Severity.LOW: "blue", Severity.MEDIUM: "yellow",
              Severity.HIGH: "red", Severity.CRITICAL: "bold magenta"}


@app.command()
def analyze(
    file: Path = typer.Argument(..., exists=True, dir_okay=False, help="Image, audio or video file to examine"),
    cases_dir: Path = typer.Option(settings.CASES_DIR, help="Root folder for case data"),
    case_id: str | None = typer.Option(None, help="Add to an existing case instead of opening a new one"),
    only: str | None = typer.Option(None, help="Comma-separated analyzer names to run"),
    exclude: str | None = typer.Option(None, help="Comma-separated analyzer names to skip"),
    quick: bool = typer.Option(False, "--quick", help="Skip deep-scan analyzers (TruFor)"),
    open_report: bool = typer.Option(False, "--open", help="Open the HTML report when done"),
) -> None:
    """Ingest an image, audio or video file as evidence and run the forensic pipeline on it."""
    selected = [s.strip() for s in only.split(",")] if only else None
    skipped = [s.strip() for s in exclude.split(",")] if exclude else None
    with console.status("Analysing...") as status:
        report, paths = analyze_media(file, cases_dir, case_id, selected, exclude=skipped, deep=not quick,
                                      progress=lambda stage, f: status.update(f"{f:4.0%}  {escape(stage)}"))

    table = Table(title=f"{file.name}  ·  sha256 {report.evidence.sha256[:16]}…", expand=True)
    for col in ("Analyzer", "Score", "Conf.", "Top finding", "ms"):
        table.add_column(col, overflow="fold")
    for r in report.results:
        if r.status != Status.OK:
            table.add_row(r.analyzer, "-", "-", f"[dim]{r.status}: {escape(r.error or '')}[/]", str(r.elapsed_ms))
            continue
        top = top_finding(r)
        finding = f"[{_SEV_STYLE[top.severity]}]{escape(top.title)}[/]" if top else ""
        score = f"{r.score:.2f}" if r.score is not None else "-"
        table.add_row(r.analyzer, score, f"{r.confidence:.2f}", finding, str(r.elapsed_ms))
    console.print(table)

    v = report.verdict
    color = "green" if v.manipulation_probability < 0.45 else "yellow" if v.manipulation_probability < 0.6 else "red"
    body = "\n".join(f"• {escape(line)}" for line in v.rationale)
    console.print(Panel(body, title=f"[bold {color}]{v.label}[/]", expand=True,
                        subtitle=f"AI generation {v.ai_generation_probability:.0%} · "
                                 f"editing {v.editing_probability:.0%}"))
    console.print(f"Integrity re-verified: {'[green]yes' if report.integrity_verified else '[red]NO'}[/]  ·  "
                  f"custody chain: {'[green]intact' if report.custody_log_valid else '[red]BROKEN'}[/]")
    console.print(f"Case [bold]{report.evidence.case_id}[/] · report: {paths['html']}")
    if open_report:
        webbrowser.open(paths["html"].resolve().as_uri())


@app.command("verify-case")
def verify_case(
    case_id: str,
    cases_dir: Path = typer.Option(settings.CASES_DIR, help="Root folder for case data"),
) -> None:
    """Check a case's custody log chain and re-hash all of its evidence."""
    store = CaseStore(cases_dir)
    log = store.log(case_id)
    if not log.path.exists():
        console.print(f"[red]No custody log for {case_id}[/]")
        raise typer.Exit(1)
    ok, msg = log.verify()
    console.print(f"Custody log: {'[green]' if ok else '[red]'}{msg}[/]")
    ingested = {e["details"]["sha256"]: e["details"]["stored_path"] for e in log.entries() if e["action"] == "ingest"}
    all_ok = ok
    for digest, path in ingested.items():
        p = Path(path)
        good = p.exists() and sha256_file(p) == digest
        all_ok &= good
        console.print(f"  {'[green]OK ' if good else '[red]BAD'}[/] {digest[:16]}…  {p.name}")
    raise typer.Exit(0 if all_ok else 1)


@app.command("analyzers")
def list_analyzers() -> None:
    """List the registered analyzers for every media type."""
    table = Table("Name", "Media", "Version", "Weight", "Description")
    for name, cls in (analyzers_for("image") | analyzers_for("audio") | analyzers_for("video")).items():
        table.add_row(name, ", ".join(cls.modalities), cls.version, str(cls.weight), cls.description)
    console.print(table)


@app.command("setup-models")
def setup_models() -> None:
    """Download the AI detector weights (Community Forensics, TruFor, AntiDeepfake)."""
    from realis.models_setup import setup_all

    setup_all(log=console.print)
    for note in (trufor.LICENSE_NOTE, antideepfake.LICENSE_NOTE):
        console.print(f"[yellow]Note:[/] {note}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Interface to bind; keep localhost unless you need LAN access"),
    port: int = typer.Option(8000),
    cases_dir: Path = typer.Option(settings.CASES_DIR, help="Root folder for case data"),
    exclude: str | None = typer.Option(None, help="Comma-separated analyzers to disable"),
    open_browser: bool = typer.Option(False, "--open", help="Open the upload page in a browser"),
) -> None:
    """Start the local web app (upload page + API)."""
    import uvicorn

    from realis.server import create_app

    skipped = [s.strip() for s in exclude.split(",")] if exclude else None
    url = f"http://{host}:{port}/"
    console.print(f"{DISPLAY_NAME} running at [bold]{url}[/]  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(cases_dir, exclude=skipped), host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
