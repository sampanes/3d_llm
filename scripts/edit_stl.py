"""
edit_stl - command-line mesh surgery for STL (and OBJ/PLY/GLB/3MF) files
=========================================================================
For editing hand-made, downloaded, or generated meshes without opening a
GUI. Every command prints a before/after summary; outputs default to
``<input>_<op>.stl`` next to the input.

Examples:
    python -m scripts.edit_stl info part.stl
    python -m scripts.edit_stl repair scan.stl
    python -m scripts.edit_stl remesh scan.stl --voxel 0.4
    python -m scripts.edit_stl scale part.stl --to-z 120
    python -m scripts.edit_stl place part.stl
    python -m scripts.edit_stl rotate part.stl --axis x --angle 90
    python -m scripts.edit_stl hollow part.stl --wall 2.5
    python -m scripts.edit_stl boolean difference body.stl cutter.stl
    python -m scripts.edit_stl cut part.stl --z 40 --keep below
    python -m scripts.edit_stl decimate part.stl --ratio 0.3
    python -m scripts.edit_stl smooth part.stl --iterations 12
    python -m scripts.edit_stl convert part.stl -o part.3mf
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from scripts import mesh_tools as mt

_AXES = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}


def _out_path(input_path: str, suffix: str, output: str | None) -> Path:
    if output:
        return Path(output)
    p = Path(input_path)
    return p.with_name(f"{p.stem}_{suffix}.stl")


def _finish(m, input_path: str, suffix: str, output: str | None) -> None:
    path = _out_path(input_path, suffix, output)
    mt.save_mesh(m, path)
    info = mt.mesh_info(m)
    s = info["size_mm"]
    wt = "watertight" if info["watertight"] else "NOT WATERTIGHT"
    click.echo(
        f"wrote {path}  |  {s[0]} x {s[1]} x {s[2]} mm, "
        f"{info['triangles']:,} tris, {wt}"
    )


@click.group()
def cli():
    """Edit mesh files from the command line."""


@cli.command("info")
@click.argument("mesh_file", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Print JSON")
def info_cmd(mesh_file, as_json):
    """Show dimensions, watertightness, volume, components."""
    info = mt.mesh_info(mt.load_mesh(mesh_file))
    if as_json:
        click.echo(json.dumps(info, indent=2))
    else:
        for k, v in info.items():
            click.echo(f"  {k:>20}: {v}")


@cli.command("repair")
@click.argument("mesh_file", type=click.Path(exists=True))
@click.option("-o", "--output", default=None, type=click.Path())
@click.option("--force-remesh", is_flag=True, help="Skip cheap fixes, go straight to voxel remesh")
@click.option("--voxel", default=None, type=float, help="Voxel size for remesh fallback (mm)")
def repair_cmd(mesh_file, output, force_remesh, voxel):
    """Fix winding/holes; voxel-remesh as a last resort if still leaky."""
    m = mt.load_mesh(mesh_file)
    fixed = mt.voxel_remesh(m, voxel) if force_remesh else mt.ensure_watertight(m, voxel)
    _finish(fixed, mesh_file, "repaired", output)


@cli.command("remesh")
@click.argument("mesh_file", type=click.Path(exists=True))
@click.option("--voxel", default=None, type=float, help="Voxel size in mm (smaller = more detail)")
@click.option("-o", "--output", default=None, type=click.Path())
def remesh_cmd(mesh_file, voxel, output):
    """Voxel-rebuild the mesh (always watertight; resamples detail)."""
    _finish(mt.voxel_remesh(mt.load_mesh(mesh_file), voxel), mesh_file, "remeshed", output)


@cli.command("scale")
@click.argument("mesh_file", type=click.Path(exists=True))
@click.option("--factor", default=None, type=float, help="Uniform scale factor")
@click.option("--to-x", default=None, type=float, help="Target X size in mm (uniform)")
@click.option("--to-y", default=None, type=float, help="Target Y size in mm (uniform)")
@click.option("--to-z", default=None, type=float, help="Target Z size in mm (uniform)")
@click.option("--stretch", is_flag=True, help="Allow non-uniform scaling when multiple targets given")
@click.option("-o", "--output", default=None, type=click.Path())
def scale_cmd(mesh_file, factor, to_x, to_y, to_z, stretch, output):
    """Scale uniformly, or to an exact bounding-box size."""
    m = mt.scale_mesh(
        mt.load_mesh(mesh_file),
        factor=factor,
        to_x=to_x,
        to_y=to_y,
        to_z=to_z,
        uniform=not stretch,
    )
    _finish(m, mesh_file, "scaled", output)


@cli.command("place")
@click.argument("mesh_file", type=click.Path(exists=True))
@click.option("--no-center", is_flag=True, help="Keep XY position, only drop to Z=0")
@click.option("-o", "--output", default=None, type=click.Path())
def place_cmd(mesh_file, no_center, output):
    """Sit the model on Z=0, centered on the XY origin."""
    _finish(mt.place_on_bed(mt.load_mesh(mesh_file), center_xy=not no_center), mesh_file, "placed", output)


@cli.command("rotate")
@click.argument("mesh_file", type=click.Path(exists=True))
@click.option("--axis", type=click.Choice(["x", "y", "z"]), required=True)
@click.option("--angle", type=float, required=True, help="Degrees (right-hand rule)")
@click.option("-o", "--output", default=None, type=click.Path())
def rotate_cmd(mesh_file, axis, angle, output):
    """Rotate about the model's center."""
    _finish(mt.rotate_mesh(mt.load_mesh(mesh_file), _AXES[axis], angle), mesh_file, "rotated", output)


@cli.command("translate")
@click.argument("mesh_file", type=click.Path(exists=True))
@click.option("--x", default=0.0, type=float)
@click.option("--y", default=0.0, type=float)
@click.option("--z", default=0.0, type=float)
@click.option("-o", "--output", default=None, type=click.Path())
def translate_cmd(mesh_file, x, y, z, output):
    """Move the model by (x, y, z) mm."""
    m = mt.load_mesh(mesh_file).copy()
    m.apply_translation([x, y, z])
    _finish(m, mesh_file, "moved", output)


@cli.command("hollow")
@click.argument("mesh_file", type=click.Path(exists=True))
@click.option("--wall", default=2.0, type=float, help="Wall thickness in mm")
@click.option("--voxel", default=None, type=float, help="Voxel size (default wall/3)")
@click.option("-o", "--output", default=None, type=click.Path())
def hollow_cmd(mesh_file, wall, voxel, output):
    """Hollow the solid, leaving a sealed shell (add drain holes after!)."""
    _finish(mt.hollow(mt.load_mesh(mesh_file), wall=wall, voxel=voxel), mesh_file, "hollow", output)


@cli.command("boolean")
@click.argument("op", type=click.Choice(["union", "difference", "intersection"]))
@click.argument("mesh_a", type=click.Path(exists=True))
@click.argument("mesh_b", type=click.Path(exists=True))
@click.option("-o", "--output", default=None, type=click.Path())
def boolean_cmd(op, mesh_a, mesh_b, output):
    """Combine two meshes (difference = A minus B)."""
    m = mt.boolean_op(mt.load_mesh(mesh_a), mt.load_mesh(mesh_b), op)
    _finish(m, mesh_a, op, output)


@cli.command("cut")
@click.argument("mesh_file", type=click.Path(exists=True))
@click.option("--x", default=None, type=float, help="Cut at this X (plane normal +X)")
@click.option("--y", default=None, type=float, help="Cut at this Y (plane normal +Y)")
@click.option("--z", default=None, type=float, help="Cut at this Z (plane normal +Z)")
@click.option("--keep", type=click.Choice(["above", "below"]), default="below")
@click.option("--no-cap", is_flag=True, help="Leave the cut face open")
@click.option("-o", "--output", default=None, type=click.Path())
def cut_cmd(mesh_file, x, y, z, keep, no_cap, output):
    """Planar cut at an axis position, keeping one capped half."""
    given = [(v, ax) for v, ax in ((x, 0), (y, 1), (z, 2)) if v is not None]
    if len(given) != 1:
        raise click.BadParameter("Give exactly one of --x / --y / --z")
    value, ax = given[0]
    origin = [0.0, 0.0, 0.0]
    origin[ax] = value
    normal = [0.0, 0.0, 0.0]
    normal[ax] = 1.0 if keep == "above" else -1.0
    m = mt.slice_plane(mt.load_mesh(mesh_file), origin, normal, cap=not no_cap)
    _finish(m, mesh_file, "cut", output)


@cli.command("decimate")
@click.argument("mesh_file", type=click.Path(exists=True))
@click.option("--faces", default=None, type=int, help="Target triangle count")
@click.option("--ratio", default=None, type=float, help="Keep this fraction of triangles")
@click.option("-o", "--output", default=None, type=click.Path())
def decimate_cmd(mesh_file, faces, ratio, output):
    """Reduce triangle count (smaller file, faster slicing)."""
    _finish(mt.decimate(mt.load_mesh(mesh_file), faces, ratio), mesh_file, "decimated", output)


@cli.command("smooth")
@click.argument("mesh_file", type=click.Path(exists=True))
@click.option("--iterations", default=10, type=int)
@click.option("-o", "--output", default=None, type=click.Path())
def smooth_cmd(mesh_file, iterations, output):
    """Taubin-smooth the surface (good after voxel remesh or scanning)."""
    _finish(mt.smooth_mesh(mt.load_mesh(mesh_file), iterations), mesh_file, "smoothed", output)


@cli.command("convert")
@click.argument("mesh_file", type=click.Path(exists=True))
@click.option("-o", "--output", required=True, type=click.Path(), help="Target file (.stl/.obj/.ply/.glb/.3mf)")
def convert_cmd(mesh_file, output):
    """Convert between mesh formats."""
    m = mt.load_mesh(mesh_file)
    mt.save_mesh(m, output)
    click.echo(f"wrote {output}")


if __name__ == "__main__":
    cli()
