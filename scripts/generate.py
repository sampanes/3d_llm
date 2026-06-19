"""
Main Generation Pipeline
=========================
End-to-end pipeline that takes a text description, sends it to an LLM,
receives generated OpenSCAD or CadQuery code, saves the source file,
exports to STL, and validates the result.

Usage:
    python -m scripts.generate --prompt "A 20-tooth spur gear" --llm openai --pipeline openscad
    python -m scripts.generate --prompt "A phone stand" --llm anthropic --model claude-sonnet-4-6 --pipeline cadquery
    python -m scripts.generate --prompt "A hexagonal vase" --llm google --few-shot
    python -m scripts.generate --prompt "Recreate this voronoi vase" --image photo.jpg --pipeline sdf --few-shot
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

# ---------------------------------------------------------------------------
# Project root and path setup
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Local imports
from scripts.llm_clients import generate as llm_generate, LLMResponse  # noqa: E402
from scripts.openscad_runner import OpenSCADRunner  # noqa: E402
from scripts.validate_stl import validate_stl, print_report  # noqa: E402

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------

PROMPTS_DIR = PROJECT_ROOT / "prompts"
OUTPUT_DIR = PROJECT_ROOT / "output"
SCAD_OUTPUT_DIR = OUTPUT_DIR / "scad"
CADQUERY_OUTPUT_DIR = OUTPUT_DIR / "cadquery"
SDF_OUTPUT_DIR = OUTPUT_DIR / "sdf"
STL_OUTPUT_DIR = OUTPUT_DIR / "stl"
EXAMPLES_DIR = PROJECT_ROOT / "examples"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _timestamp() -> str:
    """Return a filesystem-safe timestamp string."""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _slugify(text: str, max_len: int = 40) -> str:
    """Turn a prompt string into a filesystem-safe slug."""
    import re

    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_-]+", "_", slug).strip("_")
    return slug[:max_len]


def load_system_prompt(pipeline: str) -> str:
    """Load the system prompt for the given pipeline.

    Reads ``prompts/<pipeline>/system_prompt.md`` and extracts the first
    fenced code block (the docs wrap the actual prompt in a fence).
    Falls back to a built-in default if the file doesn't exist.
    """
    import re

    prompt_file = PROMPTS_DIR / pipeline / "system_prompt.md"
    if prompt_file.is_file():
        text = prompt_file.read_text(encoding="utf-8")
        fenced = re.search(r"```[^\n]*\n(.*?)```", text, re.DOTALL)
        if fenced:
            return fenced.group(1).strip()
        return text

    # Fallback defaults
    defaults = {
        "openscad": (
            "You are an expert 3D modeler. Generate valid OpenSCAD code based on "
            "the user's description. Output ONLY the OpenSCAD code wrapped in a "
            "```openscad code fence. The code must produce a single, watertight, "
            "manifold solid. Use modules for organization. Add comments explaining "
            "key dimensions and design choices. Do not include any explanatory text "
            "outside the code fence."
        ),
        "cadquery": (
            "You are an expert 3D modeler using CadQuery (Python). Generate valid "
            "CadQuery Python code based on the user's description. Output ONLY the "
            "Python code wrapped in a ```python code fence. The script must define "
            "the final solid as a variable named `result` and export it to STL using "
            "cq.exporters.export(result, 'output.stl'). The model must be a single, "
            "watertight, manifold solid. Add comments explaining key dimensions."
        ),
        "sdf": (
            "You are an expert organic 3D modeler using this repo's SDF toolkit. "
            "Generate a Python script that imports `from scripts import sdf_kit as sk` "
            "and `from scripts import organic as og`, builds the shape in millimeters "
            "with Z up sitting on z=0, meshes it with sk.mesh(...), and ends with "
            "sk.save_stl(m, 'model.stl'). Output ONLY the Python code wrapped in a "
            "```python code fence."
        ),
    }
    return defaults.get(pipeline, defaults["openscad"])


def load_few_shot_examples(pipeline: str) -> str:
    """Load few-shot examples for the pipeline.

    Primary source: ``prompts/<pipeline>/few_shot_examples.md`` (a
    self-contained markdown doc of worked examples, appended wholesale).
    Also picks up any ``examples/<pipeline>_example_*.{scad,py}`` files.
    """
    parts = []

    md_file = PROMPTS_DIR / pipeline / "few_shot_examples.md"
    if md_file.is_file():
        parts.append("\n\n--- FEW-SHOT EXAMPLES ---\n")
        parts.append(md_file.read_text(encoding="utf-8"))

    if EXAMPLES_DIR.is_dir():
        ext = "scad" if pipeline == "openscad" else "py"
        for i, ef in enumerate(sorted(EXAMPLES_DIR.glob(f"{pipeline}_example_*.{ext}")), 1):
            desc_file = ef.with_suffix(".txt")
            if not parts:
                parts.append("\n\n--- FEW-SHOT EXAMPLES ---\n")
            parts.append(f"\nExtra example {i}:")
            if desc_file.is_file():
                parts.append(f"Description: {desc_file.read_text(encoding='utf-8').strip()}")
            parts.append(f"```{ext}\n{ef.read_text(encoding='utf-8').strip()}\n```\n")

    return "\n".join(parts)


def load_template(template_path: str, pipeline: str) -> str:
    """Load a template file and return context string for the prompt."""
    tp = Path(template_path)
    if not tp.is_file():
        raise click.BadParameter(f"Template file not found: {template_path}")

    content = tp.read_text(encoding="utf-8")
    return (
        f"\n\n--- TEMPLATE / STARTING POINT ---\n"
        f"Use the following code as a starting point and modify it according "
        f"to the user's description:\n"
        f"```\n{content.strip()}\n```\n"
    )


def save_source(code: str, pipeline: str, slug: str) -> Path:
    """Save generated source code to the appropriate output directory."""
    if pipeline == "openscad":
        out_dir = SCAD_OUTPUT_DIR
        ext = ".scad"
    elif pipeline == "sdf":
        out_dir = SDF_OUTPUT_DIR
        ext = ".py"
    else:
        out_dir = CADQUERY_OUTPUT_DIR
        ext = ".py"

    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{slug}_{_timestamp()}{ext}"
    out_path = out_dir / filename
    out_path.write_text(code, encoding="utf-8")
    return out_path


def _rewrite_cadquery_export(code: str, stl_path: Path) -> str:
    """Point any CadQuery STL-export call in *code* at *stl_path*.

    Rewrites ``cq.exporters.export(var, '...stl')`` and ``.exportStl('...stl')``;
    if the script has no export call at all, appends a default one exporting
    ``result``. Pure string transform (no I/O) so it is unit-testable.
    """
    import re

    target = str(stl_path).replace("\\", "\\\\")
    code = re.sub(
        r"""cq\.exporters\.export\s*\(\s*(\w+)\s*,\s*['"][^'"]*\.stl['"]\s*\)""",
        f'cq.exporters.export(\\1, "{target}")',
        code,
    )
    code = re.sub(
        r"""\.exportStl\s*\(\s*['"][^'"]*\.stl['"]\s*\)""",
        f'.exportStl("{target}")',
        code,
    )
    if "export" not in code.lower() and "exportstl" not in code.lower():
        code += f'\n\nimport cadquery as cq\ncq.exporters.export(result, "{target}")\n'
    return code


def _rewrite_sdf_save_stl(code: str, stl_path: Path) -> str:
    """Point the ``save_stl(mesh, '...stl')`` call in *code* at *stl_path*.

    Raises RuntimeError if the generated script never calls save_stl, so the
    caller fails loudly instead of silently producing nothing. Pure string
    transform (no I/O) so it is unit-testable.
    """
    import re

    target = str(stl_path).replace("\\", "\\\\")
    code, n_subs = re.subn(
        r"""save_stl\s*\(\s*([^,()]+?)\s*,\s*['"][^'"]*\.stl['"]\s*(?:,\s*)?\)""",
        f'save_stl(\\1, "{target}")',
        code,
    )
    if n_subs == 0:
        raise RuntimeError(
            "generated script never calls save_stl(mesh, '...stl'); cannot export"
        )
    return code


def export_stl_openscad(scad_path: Path, stl_dir: Path) -> Path:
    """Use OpenSCAD to export an STL from a .scad file."""
    stl_dir.mkdir(parents=True, exist_ok=True)
    stl_path = stl_dir / scad_path.with_suffix(".stl").name

    runner = OpenSCADRunner()
    console.print("[dim]Rendering STL with OpenSCAD...[/]")
    result = runner.render_stl(scad_path, stl_path)

    if not result.success:
        error_msg = "; ".join(result.errors) if result.errors else result.stderr
        raise RuntimeError(f"OpenSCAD render failed: {error_msg}")

    console.print(
        f"[green]OK: STL rendered in {result.elapsed_seconds:.1f}s[/]"
    )
    return Path(result.output_path)


def export_stl_cadquery(py_path: Path, stl_dir: Path) -> Path:
    """Run a CadQuery Python script to export an STL.

    The script is expected to export the result to an STL file.
    We modify the export path to point to our output directory.
    """
    stl_dir.mkdir(parents=True, exist_ok=True)
    stl_path = stl_dir / py_path.with_suffix(".stl").name

    # Read the script and rewrite the export path to our target.
    code = _rewrite_cadquery_export(py_path.read_text(encoding="utf-8"), stl_path)

    # Write a temp version of the script with the corrected path
    tmp_script = py_path.with_name(py_path.stem + "_run.py")
    tmp_script.write_text(code, encoding="utf-8")

    console.print("[dim]Running CadQuery script...[/]")
    try:
        proc = subprocess.run(
            [sys.executable, str(tmp_script)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"CadQuery script failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
            )
    finally:
        # Clean up temp script
        if tmp_script.is_file():
            tmp_script.unlink()

    if not stl_path.is_file():
        raise RuntimeError(
            f"CadQuery script completed but STL not found at {stl_path}"
        )

    console.print("[green]OK: CadQuery STL export complete[/]")
    return stl_path


def export_stl_sdf(py_path: Path, stl_dir: Path) -> Path:
    """Run a generated SDF-toolkit Python script to export an STL.

    The script must end with ``sk.save_stl(<mesh>, "<anything>.stl")``;
    that output path is rewritten to point at our STL directory. The
    script runs with the project root as cwd so ``from scripts import
    sdf_kit`` resolves.
    """
    stl_dir.mkdir(parents=True, exist_ok=True)
    stl_path = stl_dir / py_path.with_suffix(".stl").name

    code = _rewrite_sdf_save_stl(py_path.read_text(encoding="utf-8"), stl_path)

    tmp_script = py_path.with_name(py_path.stem + "_run.py")
    tmp_script.write_text(code, encoding="utf-8")

    console.print("[dim]Running SDF script (meshing can take a minute or two)...[/]")
    env = os.environ.copy()
    # `python script.py` puts the script's dir on sys.path, not cwd, so the
    # project root must ride along for `from scripts import sdf_kit`.
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, str(tmp_script)],
            capture_output=True,
            text=True,
            timeout=900,
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"SDF script failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
            )
        if proc.stdout.strip():
            console.print(f"[dim]{proc.stdout.strip()}[/]")
    finally:
        if tmp_script.is_file():
            tmp_script.unlink()

    if not stl_path.is_file():
        raise RuntimeError(f"SDF script completed but STL not found at {stl_path}")

    console.print("[green]OK: SDF STL export complete[/]")
    return stl_path


# ---------------------------------------------------------------------------
# Main Pipeline Function (importable)
# ---------------------------------------------------------------------------


def run_pipeline(
    prompt: str,
    llm_provider: str = "openai",
    model: Optional[str] = None,
    pipeline: str = "openscad",
    output_dir: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    few_shot: bool = False,
    template: Optional[str] = None,
    skip_validation: bool = False,
    images: Optional[list] = None,
) -> dict:
    """Execute the full generation pipeline.

    Parameters
    ----------
    prompt : str
        Natural-language description of the 3D model.
    llm_provider : str
        LLM provider: openai, anthropic, google.
    model : str | None
        Model identifier. Uses provider default if None.
    pipeline : str
        Code generation target: openscad, cadquery, or sdf (organic).
    output_dir : str | None
        Override the base output directory.
    temperature : float
        LLM sampling temperature.
    max_tokens : int
        Maximum tokens for the LLM response.
    few_shot : bool
        Include few-shot examples in the prompt.
    template : str | None
        Path to a template file to use as starting point.
    skip_validation : bool
        Skip STL validation step.
    images : list[str] | None
        Reference image file paths sent to the LLM alongside the prompt
        (the model SEES them - shape, proportions, surface style).

    Returns
    -------
    dict
        Summary of the pipeline run with all paths and results.
    """
    result = {
        "prompt": prompt,
        "provider": llm_provider,
        "model": model,
        "pipeline": pipeline,
        "images": [str(i) for i in images] if images else [],
        "success": False,
        "source_path": None,
        "stl_path": None,
        "validation": None,
        "error": None,
    }

    slug = _slugify(prompt)

    # Resolve output directories
    if output_dir:
        base = Path(output_dir).resolve()
    else:
        base = OUTPUT_DIR

    scad_dir = base / "scad"
    cq_dir = base / "cadquery"
    sdf_dir = base / "sdf"
    stl_dir = base / "stl"

    # --- Step 1: Build the full prompt ------------------------------------
    system_prompt = load_system_prompt(pipeline)

    full_prompt = prompt
    if images:
        full_prompt = (
            f"{len(images)} reference image(s) are attached. Study them: match "
            "the overall form, proportions, and surface structure you see, "
            "combined with the text instructions below.\n\n" + full_prompt
        )
    if few_shot:
        examples = load_few_shot_examples(pipeline)
        if examples:
            full_prompt = full_prompt + examples
            console.print("[dim]Loaded few-shot examples[/]")

    if template:
        template_text = load_template(template, pipeline)
        full_prompt = full_prompt + template_text
        console.print(f"[dim]Using template: {template}[/]")

    # --- Step 2: Call the LLM ---------------------------------------------
    console.print(
        Panel(
            f"[bold]Prompt:[/] {prompt}\n"
            f"[bold]Provider:[/] {llm_provider}  |  "
            f"[bold]Model:[/] {model or 'default'}  |  "
            f"[bold]Pipeline:[/] {pipeline}"
            + (f"  |  [bold]Images:[/] {len(images)}" if images else ""),
            title="3D LLM Generation",
            border_style="blue",
        )
    )

    console.print("[dim]Calling LLM API...[/]")
    try:
        llm_response: LLMResponse = llm_generate(
            prompt=full_prompt,
            system_prompt=system_prompt,
            model=model,
            provider=llm_provider,
            temperature=temperature,
            max_tokens=max_tokens,
            images=images,
        )
    except Exception as exc:
        result["error"] = f"LLM call failed: {exc}"
        console.print(f"[red]ERROR: LLM call failed: {exc}[/]")
        return result

    code = llm_response.extracted_code
    result["model"] = llm_response.model

    if not code or len(code.strip()) < 10:
        result["error"] = "LLM returned empty or trivial code"
        console.print("[red]ERROR: LLM returned empty or trivial code[/]")
        return result

    console.print(f"[green]OK: Received {len(code)} chars of code[/]")
    if llm_response.usage:
        tokens = llm_response.usage.get(
            "total_tokens",
            sum(
                v
                for v in llm_response.usage.values()
                if isinstance(v, (int, float)) and v
            ),
        )
        console.print(f"[dim]  Tokens used: {tokens}[/]")

    # Display code preview
    lang = "openscad" if pipeline == "openscad" else "python"
    preview_lines = code.split("\n")[:25]
    preview = "\n".join(preview_lines)
    if len(code.split("\n")) > 25:
        preview += "\n// ... (truncated)"
    console.print(
        Panel(
            Syntax(preview, lang, theme="monokai", line_numbers=True),
            title="Generated Code (preview)",
            border_style="dim",
        )
    )

    # --- Step 3: Save source code -----------------------------------------
    try:
        if pipeline == "openscad":
            src_dir = scad_dir
            ext = ".scad"
        elif pipeline == "sdf":
            src_dir = sdf_dir
            ext = ".py"
        else:
            src_dir = cq_dir
            ext = ".py"

        src_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{slug}_{_timestamp()}{ext}"
        src_path = src_dir / filename
        src_path.write_text(code, encoding="utf-8")
        result["source_path"] = str(src_path)
        console.print(f"[green]OK: Source saved to {src_path}[/]")
    except Exception as exc:
        result["error"] = f"Failed to save source: {exc}"
        console.print(f"[red]ERROR: Failed to save source: {exc}[/]")
        return result

    # --- Step 4: Export STL -----------------------------------------------
    stl_dir.mkdir(parents=True, exist_ok=True)
    try:
        if pipeline == "openscad":
            stl_path = export_stl_openscad(src_path, stl_dir)
        elif pipeline == "sdf":
            stl_path = export_stl_sdf(src_path, stl_dir)
        else:
            stl_path = export_stl_cadquery(src_path, stl_dir)
        result["stl_path"] = str(stl_path)
        console.print(f"[green]OK: STL exported to {stl_path}[/]")
    except Exception as exc:
        result["error"] = f"STL export failed: {exc}"
        console.print(f"[red]ERROR: STL export failed: {exc}[/]")
        # Still partially successful: we have the source code.
        return result

    # --- Step 5: Validate STL ---------------------------------------------
    if not skip_validation:
        console.print("[dim]Validating STL...[/]")
        try:
            report = validate_stl(stl_path)
            result["validation"] = report.summary_dict()
            print_report(report)
        except Exception as exc:
            console.print(f"[yellow]WARNING: Validation error: {exc}[/]")
            result["validation"] = {"error": str(exc)}
    else:
        console.print("[dim]Skipping validation[/]")

    result["success"] = True
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command("generate")
@click.option(
    "--prompt",
    "-p",
    required=True,
    help="Text description of the 3D model to generate",
)
@click.option(
    "--llm",
    type=click.Choice(["openai", "anthropic", "google", "ollama"]),
    default="anthropic",
    envvar="DEFAULT_LLM",
    show_envvar=True,
    help="LLM provider to use (env: DEFAULT_LLM)",
)
@click.option(
    "--model",
    "-m",
    default=None,
    envvar="DEFAULT_MODEL",
    show_envvar=True,
    help="Model name (e.g. claude-opus-4-8, gpt-5.5, gemini-3.5-flash, qwen2.5-coder:14b)",
)
@click.option(
    "--pipeline",
    type=click.Choice(["openscad", "cadquery", "sdf"]),
    default="openscad",
    envvar="DEFAULT_PIPELINE",
    show_envvar=True,
    help="Code generation pipeline (sdf = organic shapes via the SDF toolkit)",
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
    help="LLM sampling temperature",
)
@click.option(
    "--max-tokens",
    default=4096,
    type=int,
    help="Maximum tokens for the LLM response",
)
@click.option(
    "--few-shot",
    is_flag=True,
    default=False,
    help="Include few-shot examples in the prompt",
)
@click.option(
    "--template",
    default=None,
    type=click.Path(),
    help="Path to a template file as starting point",
)
@click.option(
    "--skip-validation",
    is_flag=True,
    default=False,
    help="Skip STL validation step",
)
@click.option(
    "--image",
    "-i",
    "images",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Reference image(s) the LLM should match (png/jpg/webp/gif); repeatable",
)
@click.option(
    "--save-report",
    is_flag=True,
    default=False,
    help="Save a JSON report of the run",
)
def cli(
    prompt: str,
    llm: str,
    model: Optional[str],
    pipeline: str,
    output_dir: Optional[str],
    temperature: float,
    max_tokens: int,
    few_shot: bool,
    template: Optional[str],
    skip_validation: bool,
    images: tuple,
    save_report: bool,
):
    """Generate a 3D model from a text description using LLM-powered code generation."""
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
        skip_validation=skip_validation,
        images=list(images),
    )

    # Summary
    console.print()
    if result["success"]:
        console.print(
            Panel(
                "[bold green]Generation Complete[/]\n\n"
                f"Source: {result['source_path']}\n"
                f"STL:    {result['stl_path']}",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                "[bold red]Generation Failed[/]\n\n"
                f"Error: {result.get('error', 'Unknown error')}",
                border_style="red",
            )
        )

    # Optionally save report
    if save_report:
        report_dir = (
            Path(output_dir).resolve() if output_dir else OUTPUT_DIR
        ) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"report_{_timestamp()}.json"
        report_path.write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        console.print(f"[dim]Report saved to {report_path}[/]")


if __name__ == "__main__":
    cli()
