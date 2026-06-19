"""
OpenSCAD Runner
================
Wrapper around the OpenSCAD CLI that auto-detects the installation path,
renders STL files, generates preview images, and checks syntax.

Usage (as a library):
    from scripts.openscad_runner import OpenSCADRunner

    runner = OpenSCADRunner()          # auto-detects binary
    result = runner.render_stl("model.scad", "model.stl")
    result = runner.render_preview("model.scad", "preview.png")
    ok     = runner.check_syntax("model.scad")

Usage (standalone CLI):
    python -m scripts.openscad_runner render model.scad -o model.stl
    python -m scripts.openscad_runner preview model.scad -o preview.png
    python -m scripts.openscad_runner check model.scad
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import click

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    """Structured result from an OpenSCAD invocation."""

    success: bool
    command: list[str]
    return_code: int = 0
    stdout: str = ""
    stderr: str = ""
    output_path: Optional[str] = None
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


@dataclass
class CameraSettings:
    """Camera configuration for OpenSCAD preview rendering."""

    translate: tuple[float, float, float] = (0, 0, 0)
    rotate: tuple[float, float, float] = (55, 0, 25)
    distance: float = 140
    fov: float = 22.5

    # Predefined angles
    PRESETS = {
        "front": {"rotate": (0, 0, 0), "distance": 140},
        "top": {"rotate": (90, 0, 0), "distance": 140},
        "right": {"rotate": (0, 0, 90), "distance": 140},
        "iso": {"rotate": (55, 0, 25), "distance": 140},
        "back": {"rotate": (0, 0, 180), "distance": 140},
        "bottom": {"rotate": (-90, 0, 0), "distance": 140},
    }

    @classmethod
    def from_preset(cls, name: str) -> "CameraSettings":
        """Create CameraSettings from a named preset."""
        name = name.lower()
        if name not in cls.PRESETS:
            raise ValueError(
                f"Unknown preset '{name}'. Choose from: {', '.join(cls.PRESETS)}"
            )
        preset = cls.PRESETS[name]
        return cls(
            rotate=preset["rotate"],
            distance=preset["distance"],
        )

    def to_cli_arg(self) -> str:
        """Return the --camera CLI argument string."""
        tx, ty, tz = self.translate
        rx, ry, rz = self.rotate
        return f"{tx},{ty},{tz},{rx},{ry},{rz},{self.distance}"


# ---------------------------------------------------------------------------
# OpenSCAD Runner
# ---------------------------------------------------------------------------


class OpenSCADRunner:
    """Wrapper around the OpenSCAD command-line interface."""

    def __init__(
        self,
        binary_path: Optional[str] = None,
        timeout: int = 120,
    ):
        """
        Parameters
        ----------
        binary_path : str | None
            Explicit path to the OpenSCAD binary. If *None*, auto-detect.
        timeout : int
            Maximum seconds to wait for any single OpenSCAD invocation.
        """
        self.timeout = timeout
        self.binary = binary_path or self._detect_binary()
        if not self.binary:
            raise FileNotFoundError(
                "OpenSCAD binary not found. Expected the portable install at "
                "tools/openscad/, or install OpenSCAD / set OPENSCAD_PATH."
            )
        self._supports_manifold: Optional[bool] = None
        logger.info("Using OpenSCAD binary: %s", self.binary)

    @property
    def supports_manifold(self) -> bool:
        """True on 2024+ builds, which ship the much faster Manifold backend."""
        if self._supports_manifold is None:
            import re as _re

            match = _re.search(r"(\d{4})", self.version())
            self._supports_manifold = bool(match and int(match.group(1)) >= 2024)
        return self._supports_manifold

    # ----- Binary Detection ------------------------------------------------

    @staticmethod
    def _detect_binary() -> Optional[str]:
        """Try to locate the OpenSCAD executable on the current platform."""
        # 1. Project-local portable install (tools/openscad/) - preferred.
        #    On Windows, openscad.com is the console wrapper (captures output);
        #    openscad.exe is the GUI-subsystem binary.
        project_root = Path(__file__).resolve().parent.parent
        local_dir = project_root / "tools" / "openscad"
        for name in ("openscad.com", "openscad.exe", "openscad"):
            cand = local_dir / name
            if cand.is_file():
                return str(cand)

        # 2. Explicit override
        env_path = os.getenv("OPENSCAD_PATH")
        if env_path and os.path.isfile(env_path):
            return env_path

        # 3. Check PATH
        which = shutil.which("openscad")
        if which:
            return which

        system = platform.system()

        if system == "Windows":
            candidates = [
                r"C:\Program Files\OpenSCAD\openscad.exe",
                r"C:\Program Files (x86)\OpenSCAD\openscad.exe",
                os.path.expandvars(
                    r"%LOCALAPPDATA%\Programs\OpenSCAD\openscad.exe"
                ),
            ]
        elif system == "Darwin":
            candidates = [
                "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
                "/opt/homebrew/bin/openscad",
                "/usr/local/bin/openscad",
            ]
        else:  # Linux / other
            candidates = [
                "/usr/bin/openscad",
                "/usr/local/bin/openscad",
                "/snap/bin/openscad",
                os.path.expanduser("~/.local/bin/openscad"),
            ]

        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate

        return None

    # ----- Core Execution --------------------------------------------------

    def _run(self, cmd: list[str]) -> RunResult:
        """Execute *cmd* and return a structured result."""
        import time as _time

        logger.debug("Running: %s", " ".join(cmd))
        start = _time.monotonic()

        # Make bundled libraries (BOSL2 etc.) resolvable via include <...>
        env = os.environ.copy()
        lib_dir = Path(self.binary).parent / "libraries"
        if lib_dir.is_dir():
            existing = env.get("OPENSCADPATH", "")
            env["OPENSCADPATH"] = str(lib_dir) + (os.pathsep + existing if existing else "")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
            )
            elapsed = _time.monotonic() - start
            errors = []
            if proc.returncode != 0:
                errors.append(f"OpenSCAD exited with code {proc.returncode}")
            # Parse stderr for ERROR/WARNING lines
            for line in proc.stderr.splitlines():
                stripped = line.strip()
                if stripped.upper().startswith(("ERROR", "WARNING")):
                    errors.append(stripped)

            return RunResult(
                success=proc.returncode == 0,
                command=cmd,
                return_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                elapsed_seconds=round(elapsed, 2),
                errors=errors,
            )
        except subprocess.TimeoutExpired:
            elapsed = _time.monotonic() - start
            return RunResult(
                success=False,
                command=cmd,
                return_code=-1,
                stderr=f"Timed out after {self.timeout}s",
                elapsed_seconds=round(elapsed, 2),
                errors=[f"Process timed out after {self.timeout}s"],
            )
        except FileNotFoundError:
            return RunResult(
                success=False,
                command=cmd,
                return_code=-1,
                stderr="OpenSCAD binary not found",
                errors=["OpenSCAD binary not found at the configured path"],
            )

    # ----- Public Methods --------------------------------------------------

    def render_stl(
        self,
        scad_path: str | Path,
        stl_path: str | Path,
    ) -> RunResult:
        """Render a .scad file to an STL mesh.

        Parameters
        ----------
        scad_path : str | Path
            Input OpenSCAD source file.
        stl_path : str | Path
            Destination STL file path.

        Returns
        -------
        RunResult
        """
        scad_path = Path(scad_path).resolve()
        stl_path = Path(stl_path).resolve()

        if not scad_path.is_file():
            return RunResult(
                success=False,
                command=[],
                errors=[f"Input file not found: {scad_path}"],
            )

        stl_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [self.binary, "-o", str(stl_path)]
        if self.supports_manifold:
            cmd.append("--backend=Manifold")
        cmd.append(str(scad_path))
        result = self._run(cmd)
        if result.success and stl_path.is_file():
            result.output_path = str(stl_path)
        return result

    def render_preview(
        self,
        scad_path: str | Path,
        png_path: str | Path,
        camera: Optional[CameraSettings] = None,
        size: tuple[int, int] = (1024, 768),
        colorscheme: str = "Cornfield",
    ) -> RunResult:
        """Render a preview PNG image from a .scad file.

        Parameters
        ----------
        scad_path : str | Path
            Input OpenSCAD source file.
        png_path : str | Path
            Destination PNG file path.
        camera : CameraSettings | None
            Camera position. Defaults to isometric view.
        size : tuple[int, int]
            Image width and height in pixels.
        colorscheme : str
            OpenSCAD color scheme name.

        Returns
        -------
        RunResult
        """
        scad_path = Path(scad_path).resolve()
        png_path = Path(png_path).resolve()

        if not scad_path.is_file():
            return RunResult(
                success=False,
                command=[],
                errors=[f"Input file not found: {scad_path}"],
            )

        png_path.parent.mkdir(parents=True, exist_ok=True)

        if camera is None:
            camera = CameraSettings.from_preset("iso")

        cmd = [
            self.binary,
            "-o", str(png_path),
            f"--camera={camera.to_cli_arg()}",
            f"--imgsize={size[0]},{size[1]}",
            f"--colorscheme={colorscheme}",
            str(scad_path),
        ]
        result = self._run(cmd)
        if result.success and png_path.is_file():
            result.output_path = str(png_path)
        return result

    def check_syntax(self, scad_path: str | Path) -> RunResult:
        """Check a .scad file for syntax errors without rendering.

        Uses ``--export-format=echo`` to avoid actual geometry processing.

        Returns
        -------
        RunResult
            ``success`` is True if the file parsed without errors.
        """
        scad_path = Path(scad_path).resolve()

        if not scad_path.is_file():
            return RunResult(
                success=False,
                command=[],
                errors=[f"Input file not found: {scad_path}"],
            )

        # Export echo output to stdout. This parses the SCAD without rendering
        # geometry, and avoids Windows' extensionless NUL output path.
        cmd = [
            self.binary,
            "--export-format=echo",
            "-o",
            "-",
            str(scad_path),
        ]
        result = self._run(cmd)
        return result

    def version(self) -> str:
        """Return the OpenSCAD version string."""
        result = self._run([self.binary, "--version"])
        # OpenSCAD prints version to stderr
        ver = (result.stderr or result.stdout).strip()
        return ver


# ---------------------------------------------------------------------------
# CLI (standalone usage)
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """OpenSCAD runner - render STL, preview PNG, or check syntax."""
    pass


@cli.command()
@click.argument("scad_file", type=click.Path(exists=True))
@click.option("-o", "--output", default=None, help="Output STL path")
@click.option("--timeout", default=120, help="Timeout in seconds")
def render(scad_file: str, output: Optional[str], timeout: int):
    """Render a .scad file to STL."""
    if output is None:
        output = str(Path(scad_file).with_suffix(".stl"))

    runner = OpenSCADRunner(timeout=timeout)
    click.echo(f"Rendering {scad_file} -> {output}")
    result = runner.render_stl(scad_file, output)

    if result.success:
        click.secho(f"OK: STL saved to {result.output_path}", fg="green")
        click.echo(f"  Elapsed: {result.elapsed_seconds}s")
    else:
        click.secho("FAILED: render failed", fg="red")
        for err in result.errors:
            click.echo(f"  {err}")
    raise SystemExit(0 if result.success else 1)


@cli.command()
@click.argument("scad_file", type=click.Path(exists=True))
@click.option("-o", "--output", default=None, help="Output PNG path")
@click.option(
    "--angle",
    type=click.Choice(["front", "top", "right", "iso", "back", "bottom"]),
    default="iso",
    help="Camera angle preset",
)
@click.option("--width", default=1024, help="Image width")
@click.option("--height", default=768, help="Image height")
@click.option("--timeout", default=120, help="Timeout in seconds")
def preview(
    scad_file: str,
    output: Optional[str],
    angle: str,
    width: int,
    height: int,
    timeout: int,
):
    """Render a preview PNG from a .scad file."""
    if output is None:
        output = str(Path(scad_file).with_suffix(".png"))

    runner = OpenSCADRunner(timeout=timeout)
    camera = CameraSettings.from_preset(angle)
    click.echo(f"Rendering preview {scad_file} -> {output}")
    result = runner.render_preview(scad_file, output, camera=camera, size=(width, height))

    if result.success:
        click.secho(f"OK: preview saved to {result.output_path}", fg="green")
    else:
        click.secho("FAILED: preview failed", fg="red")
        for err in result.errors:
            click.echo(f"  {err}")
    raise SystemExit(0 if result.success else 1)


@cli.command()
@click.argument("scad_file", type=click.Path(exists=True))
@click.option("--timeout", default=30, help="Timeout in seconds")
def check(scad_file: str, timeout: int):
    """Check a .scad file for syntax errors."""
    runner = OpenSCADRunner(timeout=timeout)
    result = runner.check_syntax(scad_file)

    if result.success:
        click.secho(f"OK: {scad_file} syntax OK", fg="green")
    else:
        click.secho(f"FAILED: {scad_file} syntax errors", fg="red")
        for err in result.errors:
            click.echo(f"  {err}")
    raise SystemExit(0 if result.success else 1)


if __name__ == "__main__":
    cli()
