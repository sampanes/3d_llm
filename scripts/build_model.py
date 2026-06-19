"""
build_model - run a model folder end-to-end: generate, validate, preview
=========================================================================
The reproducible unit of work in this repo is a *model folder*::

    models/<name>/
        spec.md       what was asked for, in plain language + dimensions
        params.json   every tunable number (model.py reads this)
        model.py      generator script -> writes STL(s) into output/
        output/       model.stl, report.json, *_preview.png  (generated)

This runner executes ``model.py``, then validates every STL it produced
and renders preview contact sheets, writing ``output/report.json``.
Exit code is non-zero if generation or validation fails.

Usage:
    python -m scripts.build_model models/organ_coral
    python -m scripts.build_model models/organ_coral --skip-preview
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import click

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@click.command("build-model")
@click.argument("model_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--skip-preview", is_flag=True, help="Skip PNG preview rendering")
@click.option("--skip-validation", is_flag=True, help="Skip STL validation")
@click.option("--timeout", default=900, type=int, help="model.py timeout in seconds")
def cli(model_dir: str, skip_preview: bool, skip_validation: bool, timeout: int):
    """Run MODEL_DIR/model.py, then validate + preview everything it produced."""
    model_dir_p = Path(model_dir).resolve()
    model_py = model_dir_p / "model.py"
    if not model_py.is_file():
        raise click.ClickException(f"{model_dir_p} has no model.py")

    out_dir = model_dir_p / "output"
    out_dir.mkdir(exist_ok=True)

    click.echo(f"== Running {model_py.relative_to(PROJECT_ROOT) if model_py.is_relative_to(PROJECT_ROOT) else model_py}")
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(model_py)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    elapsed = time.perf_counter() - t0
    if proc.stdout.strip():
        click.echo(proc.stdout.rstrip())
    if proc.returncode != 0:
        click.echo(proc.stderr.rstrip())
        raise click.ClickException(f"model.py failed (exit {proc.returncode})")
    click.echo(f"== model.py finished in {elapsed:.1f}s")

    stls = sorted(out_dir.glob("*.stl"))
    if not stls:
        raise click.ClickException(f"model.py produced no STL files in {out_dir}")

    report = {"model_dir": str(model_dir_p), "build_seconds": round(elapsed, 1), "stls": []}
    all_pass = True

    for stl in stls:
        entry: dict = {"file": stl.name}
        if not skip_validation:
            from scripts.validate_stl import validate_stl

            v = validate_stl(stl)
            entry["validation"] = v.summary_dict()
            status = "PASS" if v.passed else "FAIL"
            if not v.passed:
                all_pass = False
            size = v.bbox_size
            click.echo(
                f"  {stl.name}: {status}  "
                f"({size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm, "
                f"{v.triangle_count:,} tris, watertight={v.is_watertight})"
            )
        if not skip_preview:
            from scripts.mesh_preview import render_preview

            png = render_preview(stl, out_path=out_dir / f"{stl.stem}_preview.png")
            entry["preview"] = Path(png).name
            click.echo(f"  preview -> {png}")
        report["stls"].append(entry)

    report["passed"] = all_pass
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    click.echo(f"== report -> {report_path}")

    if not all_pass:
        raise click.ClickException("One or more STLs failed validation")
    click.echo("== ALL CHECKS PASSED")


if __name__ == "__main__":
    cli()
