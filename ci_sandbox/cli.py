"""CLI do CI Sandbox."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import click

from ci_sandbox.models import Job, Workflow
from ci_sandbox.parser import WorkflowParser
from ci_sandbox.simulator import CISimulator

try:
    __version__ = version("ci-sandbox")
except PackageNotFoundError:
    try:
        from ci_sandbox import __version__ as _pkg_version
        __version__ = _pkg_version
    except ImportError:
        __version__ = "0.1.0"


def format_results(
    workflow: Workflow,
    jobs: dict[str, Job],
    simulator: CISimulator,
    show_steps: bool = False,
) -> str:
    lines: list[str] = []
    lines.append(click.style(f"🔧 {workflow.name}", bold=True, fg="cyan"))
    lines.append(
        click.style(
            f"   Event: {simulator.event} | Branch: {simulator.branch} | Ref: {simulator.ref}",
            fg="bright_black",
        )
    )
    lines.append("")

    status_icon = {
        "success": click.style("✓", fg="green", bold=True),
        "failure": click.style("✗", fg="red", bold=True),
        "skipped": click.style("○", fg="yellow"),
        "running": click.style("⟳", fg="blue"),
        "pending": click.style("…", fg="bright_black"),
    }

    for group_idx, group in enumerate(simulator.execution_order):
        if group_idx > 0:
            lines.append(click.style("  ↓", fg="bright_black"))
        for job_name in group:
            job = jobs[job_name]
            icon = status_icon.get(job.status, "?")
            color = {
                "success": "green",
                "failure": "red",
                "skipped": "yellow",
                "pending": "bright_black",
            }.get(job.status, "white")

            line = f"  {icon} {click.style(job_name, fg=color)}"
            if job.status == "skipped" and job.skipped_because:
                line += click.style(f" ({job.skipped_because})", fg="bright_black")
            if job.runs_on:
                line += click.style(f" [{job.runs_on}]", fg="bright_black")
            lines.append(line)

            if show_steps and job.steps:
                for step in job.steps:
                    step_name = step.name or step.uses or step.run[:50] or "(unnamed)"
                    lines.append(
                        click.style(f"      • {step_name}", fg="bright_black")
                    )

    total = len(jobs)
    ok = sum(1 for j in jobs.values() if j.status == "success")
    fail = sum(1 for j in jobs.values() if j.status == "failure")
    skip = sum(1 for j in jobs.values() if j.status == "skipped")

    lines.append("")
    summary_parts = [f"{ok} success", f"{skip} skipped"]
    if fail:
        summary_parts.insert(1, click.style(f"{fail} failed", fg="red", bold=True))
    lines.append(
        click.style(
            f"  ══ {' · '.join(summary_parts)} ({total} jobs) ══",
            fg="cyan" if not fail else "red",
            bold=True,
        )
    )
    return "\n".join(lines)


@click.group()
@click.version_option(__version__, "-v", "--version", package_name="ci-sandbox")
def cli():
    """CI Sandbox — Simule pipelines CI localmente sem executar."""


@cli.command()
@click.argument("workflow_path", type=click.Path(exists=True, path_type=Path))
@click.option("--event", default="push", help="Tipo de evento (push, pull_request, etc)")
@click.option("--branch", default="main", help="Branch para simular")
@click.option("--ref", default=None, help="Ref completo (ex: refs/heads/main)")
@click.option("--secret", "-s", multiple=True, help="Secrets no formato KEY=VALUE")
@click.option("--input", "-i", "input_args", multiple=True, help="Inputs no formato KEY=VALUE")
@click.option("--steps", is_flag=True, help="Mostrar steps de cada job")
def simulate(
    workflow_path: Path,
    event: str,
    branch: str,
    ref: str | None,
    secret: tuple[str, ...],
    input_args: tuple[str, ...],
    steps: bool,
):
    """Simula execução de um workflow."""
    parser = WorkflowParser(workflow_path)
    try:
        workflow = parser.parse()
    except Exception as e:
        click.echo(click.style(f"❌ Erro ao parsear workflow: {e}", fg="red"))
        sys.exit(1)

    secrets_dict = {}
    for s in secret:
        if "=" in s:
            k, v = s.split("=", 1)
            secrets_dict[k] = v

    inputs_dict = {}
    for i in input_args:
        if "=" in i:
            k, v = i.split("=", 1)
            inputs_dict[k] = v

    simulator = CISimulator(
        workflow,
        event=event,
        branch=branch,
        ref=ref,
        secrets=secrets_dict,
        inputs=inputs_dict,
    )

    jobs = simulator.run()
    output = format_results(workflow, jobs, simulator, show_steps=steps)
    click.echo(output)


@cli.command("list-workflows")
@click.option(
    "--dir",
    "workflows_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path(".github/workflows"),
    help="Diretório de workflows",
)
def list_workflows(workflows_dir: Path):
    """Lista workflows disponíveis."""
    files = sorted(workflows_dir.glob("*.y*ml"))
    if not files:
        click.echo(click.style("Nenhum workflow encontrado.", fg="yellow"))
        return
    for f in files:
        parser = WorkflowParser(f)
        try:
            wf = parser.parse()
            jobs_count = len(wf.jobs)
            click.echo(
                f"  {click.style(f.name, fg='cyan')} — {wf.name} ({jobs_count} jobs)"
            )
        except Exception as e:
            click.echo(
                f"  {click.style(f.name, fg='red')} — erro: {e}"
            )


if __name__ == "__main__":
    cli()
