"""
Render Preview Script
======================
Renders preview PNG images from OpenSCAD .scad files using the OpenSCAD CLI.
Supports multiple camera angles, configurable image size, and batch rendering
of all .scad files in a directory.

Usage:
    python -m scripts.render_preview model.scad
    python -m scripts.render_preview model.scad --angle top --width 1920 --height 1080
    python -m scripts.render_preview --batch output/scad/ -o output/previews/
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

from scripts.openscad_runner import CameraSettings, OpenSCADRunner

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Available camera angles (maps to CameraSettings presets)
# ---------------------------------------------------------------------------

ANGLE_CHOICES = list(CameraSettings.PRESETS.keys())


# ---------------------------------------------------------------------------
# Core Rendering Functions
# ---------------------------------------------------------------------------


def render_single(
    scad_path: str | Path,
    output_path: Optional[str | Path] = None,
    angle: str = "iso",
    width: int = 1024,
    height: int = 768,
    colorscheme: str = "Cornfield",
    runner: Optional[OpenSCADRunner] = None,
) -> dict:
    """Render a single .scad file to a PNG preview.

    Parameters
    ----------
    scad_path : str | Path
        Path to the .scad source file.
    output_path : str | Path | None
        Destination PNG path. Defaults to ``<scad_stem>_<angle>.png``
        next to the source file.
    angle : str
        Camera preset name (front, top, right, iso, back, bottom).
    width, height : int
        Image dimensions in pixels.
    colorscheme : str
        OpenSCAD color scheme.
    runner : OpenSCADRunner | None
        Re-use an existing runner instance for batch operations.

    Returns
    -------
    dict
        Result with keys: success, scad, png, elapsed, errors.
    """
    scad_path = Path(scad_path).resolve()

    if output_path is None:
        output_path = scad_path.with_name(f"{scad_path.stem}_{angle}.png")
    else:
        output_path = Path(output_path).resolve()

    if runner is None:
        runner = OpenSCADRunner()

    camera = CameraSettings.from_preset(angle)
    result = runner.render_preview(
        scad_path,
        output_path,
        camera=camera,
        size=(width, height),
        colorscheme=colorscheme,
    )

    return {
        "success": result.success,
        "scad": str(scad_path),
        "png": result.output_path,
        "elapsed": result.elapsed_seconds,
        "errors": result.errors,
    }


def render_multi_angle(
    scad_path: str | Path,
    output_dir: Optional[str | Path] = None,
    angles: Optional[list[str]] = None,
    width: int = 1024,
    height: int = 768,
    colorscheme: str = "Cornfield",
    runner: Optional[OpenSCADRunner] = None,
) -> list[dict]:
    """Render a single .scad file from multiple camera angles.

    Parameters
    ----------
    scad_path : str | Path
        Path to the .scad source file.
    output_dir : str | Path | None
        Directory for output PNGs. Defaults to same directory as source.
    angles : list[str] | None
        Camera presets. Defaults to all available presets.
    width, height : int
        Image dimensions in pixels.
    colorscheme : str
        OpenSCAD color scheme.
    runner : OpenSCADRunner | None
        Re-use an existing runner instance.

    Returns
    -------
    list[dict]
        One result dict per angle.
    """
    scad_path = Path(scad_path).resolve()
    if angles is None:
        angles = ANGLE_CHOICES

    if output_dir is None:
        output_dir = scad_path.parent
    else:
        output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if runner is None:
        runner = OpenSCADRunner()

    results = []
    for angle in angles:
        png_name = f"{scad_path.stem}_{angle}.png"
        png_path = output_dir / png_name
        r = render_single(
            scad_path,
            png_path,
            angle=angle,
            width=width,
            height=height,
            colorscheme=colorscheme,
            runner=runner,
        )
        results.append(r)

    return results


def render_batch(
    input_dir: str | Path,
    output_dir: Optional[str | Path] = None,
    angle: str = "iso",
    width: int = 1024,
    height: int = 768,
    colorscheme: str = "Cornfield",
) -> list[dict]:
    """Render all .scad files in a directory.

    Parameters
    ----------
    input_dir : str | Path
        Directory containing .scad files.
    output_dir : str | Path | None
        Directory for output PNGs. Defaults to ``input_dir/previews/``.
    angle : str
        Camera preset.
    width, height : int
        Image dimensions in pixels.
    colorscheme : str
        OpenSCAD color scheme.

    Returns
    -------
    list[dict]
        One result dict per .scad file.
    """
    input_dir = Path(input_dir).resolve()
    if not input_dir.is_dir():
        raise click.BadParameter(f"Not a directory: {input_dir}")

    scad_files = sorted(input_dir.glob("*.scad"))
    if not scad_files:
        console.print(f"[yellow]No .scad files found in {input_dir}[/]")
        return []

    if output_dir is None:
        output_dir = input_dir / "previews"
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    runner = OpenSCADRunner()
    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task("Rendering previews...", total=len(scad_files))
        for scad in scad_files:
            png_path = output_dir / f"{scad.stem}_{angle}.png"
            r = render_single(
                scad,
                png_path,
                angle=angle,
                width=width,
                height=height,
                colorscheme=colorscheme,
                runner=runner,
            )
            results.append(r)
            progress.advance(task)

    return results


# ---------------------------------------------------------------------------
# Result Display
# ---------------------------------------------------------------------------


def print_results(results: list[dict]) -> None:
    """Display render results in a rich table."""
    table = Table(title="Render Results", show_lines=True)
    table.add_column("File", style="cyan")
    table.add_column("Output", style="white")
    table.add_column("Time (s)", justify="right")
    table.add_column("Status", justify="center")

    for r in results:
        scad_name = Path(r["scad"]).name
        png_name = Path(r["png"]).name if r["png"] else "-"
        elapsed = f"{r['elapsed']:.1f}"
        status = "[green]OK[/]" if r["success"] else "[red]FAIL[/]"
        table.add_row(scad_name, png_name, elapsed, status)

    console.print(table)

    succeeded = sum(1 for r in results if r["success"])
    total = len(results)
    console.print(
        f"\n[bold]{succeeded}/{total}[/] previews rendered successfully."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command("render-preview")
@click.argument("input_path", type=click.Path(exists=True))
@click.option(
    "-o",
    "--output",
    default=None,
    type=click.Path(),
    help="Output path (file for single, directory for batch)",
)
@click.option(
    "--angle",
    type=click.Choice(ANGLE_CHOICES),
    default="iso",
    help="Camera angle preset",
)
@click.option(
    "--all-angles",
    is_flag=True,
    default=False,
    help="Render from all available camera angles",
)
@click.option("--width", default=1024, help="Image width in pixels")
@click.option("--height", default=768, help="Image height in pixels")
@click.option("--colorscheme", default="Cornfield", help="OpenSCAD color scheme")
@click.option(
    "--batch",
    is_flag=True,
    default=False,
    help="Treat INPUT_PATH as a directory and render all .scad files",
)
def cli(
    input_path: str,
    output: Optional[str],
    angle: str,
    all_angles: bool,
    width: int,
    height: int,
    colorscheme: str,
    batch: bool,
):
    """Render preview PNG(s) from OpenSCAD .scad files."""
    input_p = Path(input_path)

    # Batch mode: render all .scad files in a directory
    if batch or input_p.is_dir():
        results = render_batch(
            input_p,
            output_dir=output,
            angle=angle,
            width=width,
            height=height,
            colorscheme=colorscheme,
        )
        print_results(results)
        return

    # Single file with all angles
    if all_angles:
        results = render_multi_angle(
            input_p,
            output_dir=output,
            width=width,
            height=height,
            colorscheme=colorscheme,
        )
        print_results(results)
        return

    # Single file, single angle
    r = render_single(
        input_p,
        output_path=output,
        angle=angle,
        width=width,
        height=height,
        colorscheme=colorscheme,
    )
    if r["success"]:
        console.print(f"[green]OK: Preview saved to {r['png']}[/]")
    else:
        console.print("[red]ERROR: Preview rendering failed[/]")
        for err in r["errors"]:
            console.print(f"  [red]{err}[/]")


if __name__ == "__main__":
    cli()
