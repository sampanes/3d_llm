"""
STL Validation Script
======================
Loads an STL file with trimesh and runs a battery of quality checks:
watertightness, valid volume, bounding box, triangle count, surface area,
and volume. Optionally repairs the mesh and exports the fixed version.

Usage (standalone):
    python -m scripts.validate_stl model.stl
    python -m scripts.validate_stl model.stl --fix --output fixed.stl

Usage (as a library):
    from scripts.validate_stl import validate_stl, ValidationReport

    report = validate_stl("model.stl")
    print(report.passed)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import click
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class ValidationReport:
    """Results of an STL validation run."""

    file_path: str
    file_size_bytes: int = 0

    # Geometry checks
    is_watertight: bool = False
    is_volume: bool = False
    is_empty: bool = True

    # Metrics
    triangle_count: int = 0
    vertex_count: int = 0
    surface_area: float = 0.0
    volume: float = 0.0

    # Bounding box (min_x, min_y, min_z, max_x, max_y, max_z)
    bbox_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_size: tuple[float, float, float] = (0.0, 0.0, 0.0)

    # Euler characteristic and edge analysis
    euler_number: Optional[int] = None
    edges_total: int = 0

    # Errors / warnings
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Overall pass/fail
    passed: bool = False

    # If repair was done
    repaired: bool = False
    repaired_path: Optional[str] = None

    def summary_dict(self) -> dict:
        """Return a flat dictionary suitable for JSON / tabular output."""
        return {
            "file": self.file_path,
            "passed": self.passed,
            "watertight": self.is_watertight,
            "volume_valid": self.is_volume,
            "triangles": self.triangle_count,
            "vertices": self.vertex_count,
            "surface_area": round(self.surface_area, 4),
            "volume": round(self.volume, 4),
            "bbox_size": [round(v, 4) for v in self.bbox_size],
            "repaired": self.repaired,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Core Validation
# ---------------------------------------------------------------------------


def validate_stl(
    stl_path: str | Path,
    fix: bool = False,
    output_path: Optional[str | Path] = None,
) -> ValidationReport:
    """Validate an STL file and optionally repair it.

    Parameters
    ----------
    stl_path : str | Path
        Path to the input STL file.
    fix : bool
        If True, attempt to repair the mesh using trimesh.
    output_path : str | Path | None
        Where to save the repaired mesh.  Defaults to
        ``<original_stem>_fixed.stl`` in the same directory.

    Returns
    -------
    ValidationReport
    """
    import trimesh

    stl_path = Path(stl_path).resolve()
    report = ValidationReport(file_path=str(stl_path))

    # --- File-level checks -------------------------------------------------
    if not stl_path.is_file():
        report.errors.append(f"File not found: {stl_path}")
        return report

    report.file_size_bytes = stl_path.stat().st_size
    if report.file_size_bytes == 0:
        report.errors.append("File is empty (0 bytes)")
        return report

    # --- Load mesh ---------------------------------------------------------
    try:
        mesh = trimesh.load(str(stl_path), force="mesh")
    except Exception as exc:
        report.errors.append(f"Failed to load STL: {exc}")
        return report

    if mesh.is_empty:
        report.is_empty = True
        report.errors.append("Mesh contains no geometry")
        return report

    report.is_empty = False

    # --- Geometry metrics --------------------------------------------------
    report.triangle_count = len(mesh.faces)
    report.vertex_count = len(mesh.vertices)
    report.is_watertight = bool(mesh.is_watertight)
    report.is_volume = bool(mesh.is_volume)
    report.surface_area = float(mesh.area)

    if mesh.is_volume:
        report.volume = float(mesh.volume)
    else:
        report.warnings.append(
            "Mesh is not a valid volume - volume may be inaccurate"
        )
        try:
            report.volume = float(mesh.volume)
        except Exception:
            report.volume = 0.0

    # Bounding box
    bbox = mesh.bounding_box.bounds  # (2, 3) array: [[min], [max]]
    report.bbox_min = tuple(np.round(bbox[0], 4).tolist())
    report.bbox_max = tuple(np.round(bbox[1], 4).tolist())
    report.bbox_size = tuple(
        np.round(bbox[1] - bbox[0], 4).tolist()
    )

    # Euler number
    try:
        report.euler_number = int(mesh.euler_number)
    except Exception as exc:
        logger.debug("Could not compute euler_number: %s", exc)

    # Edge count
    try:
        report.edges_total = len(mesh.edges)
    except Exception as exc:
        logger.debug("Could not compute edge count: %s", exc)

    # --- Quality checks ----------------------------------------------------
    if not report.is_watertight:
        report.warnings.append("Mesh is not watertight (has holes/gaps)")

    if report.triangle_count < 4:
        report.warnings.append(
            f"Very low triangle count ({report.triangle_count})"
        )

    if report.surface_area <= 0:
        report.errors.append("Surface area is zero or negative")

    # Degenerate triangle check (near-zero-area faces)
    try:
        degen_count = int((mesh.area_faces < 1e-10).sum())
        if degen_count > 0:
            report.warnings.append(
                f"{degen_count} degenerate (zero-area) triangles detected"
            )
    except Exception as exc:
        logger.debug("Could not check degenerate triangles: %s", exc)

    # --- Repair ------------------------------------------------------------
    if fix:
        try:
            trimesh.repair.fix_normals(mesh)
            trimesh.repair.fill_holes(mesh)
            trimesh.repair.fix_winding(mesh)

            if output_path is None:
                output_path = stl_path.with_stem(stl_path.stem + "_fixed")
            output_path = Path(output_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)

            mesh.export(str(output_path))
            report.repaired = True
            report.repaired_path = str(output_path)
            report.is_watertight = bool(mesh.is_watertight)
            report.is_volume = bool(mesh.is_volume)
            logger.info("Repaired mesh saved to %s", output_path)
        except Exception as exc:
            report.errors.append(f"Repair failed: {exc}")

    # --- Overall verdict ---------------------------------------------------
    report.passed = (
        report.is_watertight
        and report.is_volume
        and report.triangle_count >= 4
        and report.surface_area > 0
        and len(report.errors) == 0
    )

    return report


# ---------------------------------------------------------------------------
# Rich Console Output
# ---------------------------------------------------------------------------


def print_report(report: ValidationReport) -> None:
    """Pretty-print a validation report using rich."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()

    # Header
    status = "[bold green]PASSED[/]" if report.passed else "[bold red]FAILED[/]"
    console.print(
        Panel(
            f"[bold]{report.file_path}[/]\nStatus: {status}",
            title="STL Validation Report",
            border_style="green" if report.passed else "red",
        )
    )

    # Metrics table
    table = Table(title="Mesh Metrics", show_lines=True)
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_column("Status", justify="center")

    def _yn(val: bool) -> str:
        return "[green]Yes[/]" if val else "[red]No[/]"

    table.add_row("Watertight", str(report.is_watertight), _yn(report.is_watertight))
    table.add_row("Valid Volume", str(report.is_volume), _yn(report.is_volume))
    table.add_row("Triangles", f"{report.triangle_count:,}", "")
    table.add_row("Vertices", f"{report.vertex_count:,}", "")
    table.add_row("Surface Area", f"{report.surface_area:,.4f}", "")
    table.add_row("Volume", f"{report.volume:,.4f}", "")
    table.add_row(
        "Bounding Box",
        f"{report.bbox_size[0]:.2f} x {report.bbox_size[1]:.2f} x {report.bbox_size[2]:.2f}",
        "",
    )
    table.add_row("File Size", f"{report.file_size_bytes:,} bytes", "")

    if report.euler_number is not None:
        table.add_row("Euler Number", str(report.euler_number), "")

    console.print(table)

    # Errors
    if report.errors:
        console.print("\n[bold red]Errors:[/]")
        for e in report.errors:
            console.print(f"  [red]- {e}[/]")

    # Warnings
    if report.warnings:
        console.print("\n[bold yellow]Warnings:[/]")
        for w in report.warnings:
            console.print(f"  [yellow]- {w}[/]")

    # Repair info
    if report.repaired:
        console.print(
            f"\n[bold green]Repaired mesh saved to:[/] {report.repaired_path}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command("validate-stl")
@click.argument("stl_file", type=click.Path(exists=True))
@click.option(
    "--fix", is_flag=True, default=False, help="Attempt to repair the mesh"
)
@click.option(
    "-o",
    "--output",
    default=None,
    type=click.Path(),
    help="Output path for repaired STL",
)
@click.option("--json", "as_json", is_flag=True, help="Output results as JSON")
def cli(stl_file: str, fix: bool, output: Optional[str], as_json: bool):
    """Validate an STL file for 3D printing / rendering quality."""
    report = validate_stl(stl_file, fix=fix, output_path=output)

    if as_json:
        import json

        click.echo(json.dumps(report.summary_dict(), indent=2))
    else:
        print_report(report)

    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    cli()
