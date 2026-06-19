"""
Batch Generation Script
========================
Reads a YAML or JSON file containing a list of model descriptions,
generates each one through the generation pipeline, and produces a
summary report. Supports parallel generation with configurable workers.

Usage:
    python -m scripts.batch_generate jobs.yaml
    python -m scripts.batch_generate jobs.json --workers 4
    python -m scripts.batch_generate jobs.yaml --llm anthropic --pipeline cadquery

Job file format (YAML):
    - prompt: "A 20-tooth spur gear"
      pipeline: openscad
      llm: openai
      model: gpt-4o
    - prompt: "A phone stand with cable slot"
    - prompt: "A hexagonal vase, 10cm tall"
      few_shot: true

Job file format (JSON):
    [
      {"prompt": "A 20-tooth spur gear", "pipeline": "openscad"},
      {"prompt": "A phone stand with cable slot"}
    ]
"""

from __future__ import annotations

import json
import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.panel import Panel

from scripts.generate import run_pipeline, OUTPUT_DIR

logger = logging.getLogger(__name__)
console = Console()


# ---------------------------------------------------------------------------
# Job File Parsing
# ---------------------------------------------------------------------------


def load_jobs(path: str | Path) -> list[dict]:
    """Load generation jobs from a YAML or JSON file.

    Each job must have at least a ``prompt`` key. Optional keys:
    ``pipeline``, ``llm``, ``model``, ``temperature``, ``max_tokens``,
    ``few_shot``, ``template``.
    """
    path = Path(path).resolve()
    suffix = path.suffix.lower()

    if suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML is required for YAML job files. "
                "Install it with: pip install pyyaml"
            )
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    elif suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        raise click.BadParameter(
            f"Unsupported file format '{suffix}'. Use .yaml, .yml, or .json"
        )

    if not isinstance(data, list):
        raise click.BadParameter(
            "Job file must contain a list of job objects at the top level"
        )

    # Validate each job
    for i, job in enumerate(data):
        if not isinstance(job, dict):
            raise click.BadParameter(f"Job #{i + 1} must be a dictionary")
        if "prompt" not in job:
            raise click.BadParameter(f"Job #{i + 1} missing required 'prompt' key")

    return data


# ---------------------------------------------------------------------------
# Single Job Execution (for threading)
# ---------------------------------------------------------------------------


def _run_single_job(
    job: dict,
    job_index: int,
    defaults: dict,
) -> dict:
    """Execute a single generation job and return the result.

    Parameters
    ----------
    job : dict
        Job definition with at least a ``prompt`` key.
    job_index : int
        1-based job number for logging.
    defaults : dict
        Default values for optional fields (llm, pipeline, etc.).

    Returns
    -------
    dict
        Pipeline result augmented with ``job_index``.
    """
    # Merge job-specific overrides with defaults
    prompt = job["prompt"]
    llm = job.get("llm", defaults.get("llm", "openai"))
    model = job.get("model", defaults.get("model", None))
    pipeline = job.get("pipeline", defaults.get("pipeline", "openscad"))
    temperature = job.get("temperature", defaults.get("temperature", 0.7))
    max_tokens = job.get("max_tokens", defaults.get("max_tokens", 4096))
    few_shot = job.get("few_shot", defaults.get("few_shot", False))
    template = job.get("template", defaults.get("template", None))
    output_dir = job.get("output_dir", defaults.get("output_dir", None))

    logger.info("Job %d: %s [%s/%s]", job_index, prompt, llm, pipeline)

    try:
        result = run_pipeline(
            prompt=prompt,
            llm_provider=llm,
            model=model,
            pipeline=pipeline,
            output_dir=output_dir,
            temperature=temperature,
            max_tokens=max_tokens,
            few_shot=few_shot,
            template=template,
            skip_validation=False,
        )
    except Exception as exc:
        result = {
            "prompt": prompt,
            "provider": llm,
            "model": model,
            "pipeline": pipeline,
            "success": False,
            "error": str(exc),
            "source_path": None,
            "stl_path": None,
            "validation": None,
        }

    result["job_index"] = job_index
    return result


# ---------------------------------------------------------------------------
# Batch Runner
# ---------------------------------------------------------------------------


def run_batch(
    jobs: list[dict],
    workers: int = 1,
    defaults: Optional[dict] = None,
) -> list[dict]:
    """Run a batch of generation jobs.

    Parameters
    ----------
    jobs : list[dict]
        List of job definitions.
    workers : int
        Number of parallel workers. Use 1 for sequential execution.
    defaults : dict | None
        Default values for optional job fields.

    Returns
    -------
    list[dict]
        List of results, one per job.
    """
    if defaults is None:
        defaults = {}

    results: list[dict] = []

    if workers <= 1:
        # Sequential execution with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Generating models...", total=len(jobs))
            for i, job in enumerate(jobs, 1):
                progress.update(
                    task, description=f"Job {i}/{len(jobs)}: {job['prompt'][:40]}..."
                )
                result = _run_single_job(job, i, defaults)
                results.append(result)
                progress.advance(task)
    else:
        # Parallel execution
        console.print(f"[dim]Running {len(jobs)} jobs with {workers} workers[/]")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_run_single_job, job, i, defaults): i
                for i, job in enumerate(jobs, 1)
            }
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Generating models...", total=len(jobs))
                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
                    progress.advance(task)

    # Sort by job_index
    results.sort(key=lambda r: r.get("job_index", 0))
    return results


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------


def print_summary(results: list[dict]) -> None:
    """Print a summary table of batch results."""
    table = Table(title="Batch Generation Summary", show_lines=True)
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("Prompt", style="cyan", max_width=40)
    table.add_column("Provider", style="white")
    table.add_column("Pipeline", style="white")
    table.add_column("Source", style="dim", max_width=30)
    table.add_column("STL", style="dim", max_width=30)
    table.add_column("Valid", justify="center")
    table.add_column("Status", justify="center")

    for r in results:
        idx = str(r.get("job_index", "?"))
        prompt = r.get("prompt", "-")[:40]
        provider = r.get("provider", "-")
        pipeline = r.get("pipeline", "-")

        source = Path(r["source_path"]).name if r.get("source_path") else "-"
        stl = Path(r["stl_path"]).name if r.get("stl_path") else "-"

        # Validation status
        validation = r.get("validation")
        if validation and isinstance(validation, dict):
            valid = "[green]OK[/]" if validation.get("passed") else "[red]FAIL[/]"
        else:
            valid = "[dim]-[/]"

        status = "[green]OK[/]" if r.get("success") else "[red]FAIL[/]"

        table.add_row(idx, prompt, provider, pipeline, source, stl, valid, status)

    console.print(table)

    # Summary stats
    total = len(results)
    succeeded = sum(1 for r in results if r.get("success"))
    failed = total - succeeded

    console.print(
        f"\n[bold]Total:[/] {total}  |  "
        f"[green]Succeeded:[/] {succeeded}  |  "
        f"[red]Failed:[/] {failed}"
    )

    if failed > 0:
        console.print("\n[bold red]Failed jobs:[/]")
        for r in results:
            if not r.get("success"):
                idx = r.get("job_index", "?")
                err = r.get("error", "Unknown error")
                console.print(f"  Job {idx}: {err}")


def save_report(results: list[dict], output_dir: Path) -> Path:
    """Save the batch report as a JSON file."""
    report_dir = output_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"batch_report_{ts}.json"

    report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "total_jobs": len(results),
        "succeeded": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "results": results,
    }

    report_path.write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    return report_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command("batch-generate")
@click.argument("job_file", type=click.Path(exists=True))
@click.option(
    "--workers",
    "-w",
    default=1,
    type=int,
    help="Number of parallel workers (default: 1 = sequential)",
)
@click.option(
    "--llm",
    type=click.Choice(["openai", "anthropic", "google", "ollama"]),
    default="anthropic",
    help="Default LLM provider (can be overridden per job)",
)
@click.option(
    "--model",
    "-m",
    default=None,
    help="Default model name (can be overridden per job)",
)
@click.option(
    "--pipeline",
    type=click.Choice(["openscad", "cadquery"]),
    default="openscad",
    help="Default pipeline (can be overridden per job)",
)
@click.option(
    "--output-dir",
    "-o",
    default=None,
    type=click.Path(),
    help="Override output directory",
)
@click.option(
    "--temperature",
    "-t",
    default=0.7,
    type=float,
    help="Default LLM temperature",
)
@click.option(
    "--no-report",
    is_flag=True,
    default=False,
    help="Skip saving the JSON report",
)
def cli(
    job_file: str,
    workers: int,
    llm: str,
    model: Optional[str],
    pipeline: str,
    output_dir: Optional[str],
    temperature: float,
    no_report: bool,
):
    """Run batch 3D model generation from a YAML/JSON job file."""
    console.print(
        Panel(
            f"[bold]Job file:[/] {job_file}\n"
            f"[bold]Workers:[/] {workers}  |  "
            f"[bold]Default LLM:[/] {llm}  |  "
            f"[bold]Default pipeline:[/] {pipeline}",
            title="Batch Generation",
            border_style="blue",
        )
    )

    # Load jobs
    jobs = load_jobs(job_file)
    console.print(f"[green]Loaded {len(jobs)} jobs[/]")

    # Build defaults dict
    defaults = {
        "llm": llm,
        "model": model,
        "pipeline": pipeline,
        "temperature": temperature,
        "output_dir": output_dir,
    }

    # Run
    results = run_batch(jobs, workers=workers, defaults=defaults)

    # Print summary
    console.print()
    print_summary(results)

    # Save report
    if not no_report:
        report_base = Path(output_dir).resolve() if output_dir else OUTPUT_DIR
        report_path = save_report(results, report_base)
        console.print(f"\n[dim]Report saved to {report_path}[/]")


if __name__ == "__main__":
    cli()
