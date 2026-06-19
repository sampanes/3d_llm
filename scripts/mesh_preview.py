"""
Mesh Preview - render any mesh file to PNG without OpenSCAD
============================================================
Renders STL/OBJ/PLY/GLB/3MF to a multi-view contact sheet (or single
views) using PyVista offscreen. This is the visual-feedback half of the
agent loop: build a mesh, render it, *look at the image*, adjust, repeat.

Usage:
    python -m scripts.mesh_preview model.stl
    python -m scripts.mesh_preview model.stl -o shot.png --views iso,front,top
    python -m scripts.mesh_preview model.stl --separate     # one PNG per view

All ortho views use the same scale, so proportions are comparable across
panels. The header lists exact bounding-box dimensions in mm.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

# (direction the camera sits along, up vector)
VIEWS = {
    "iso": ((1.0, -1.0, 0.75), (0, 0, 1)),
    "front": ((0.0, -1.0, 0.0), (0, 0, 1)),
    "back": ((0.0, 1.0, 0.0), (0, 0, 1)),
    "right": ((1.0, 0.0, 0.0), (0, 0, 1)),
    "left": ((-1.0, 0.0, 0.0), (0, 0, 1)),
    "top": ((0.0, 0.0, 1.0), (0, 1, 0)),
    "bottom": ((0.0, 0.0, -1.0), (0, -1, 0)),
}
DEFAULT_VIEWS = ("iso", "front", "right", "top")


def _render_view(pd, bounds, view: str, size: int, color: str, show_grid: bool):
    import pyvista as pv

    direction, up = VIEWS[view]
    lo = np.asarray(bounds[0::2], dtype=float)
    hi = np.asarray(bounds[1::2], dtype=float)
    center = (lo + hi) / 2
    max_ext = float(max(hi - lo))
    d = np.asarray(direction, dtype=float)
    d /= np.linalg.norm(d)
    pos = center + d * max_ext * 3.0

    p = pv.Plotter(off_screen=True, window_size=(size, size))
    p.set_background("white")
    p.add_mesh(pd, color=color, smooth_shading=True, specular=0.25, specular_power=8)
    p.camera_position = [tuple(pos), tuple(center), tuple(up)]
    p.camera.parallel_projection = True
    p.camera.parallel_scale = max_ext * 0.62
    p.add_axes(line_width=2)
    if show_grid:
        p.show_bounds(
            grid="back",
            location="outer",
            color="gray",
            font_size=9,
            fmt="%.0f",
            xtitle="X mm",
            ytitle="Y mm",
            ztitle="Z mm",
        )
    img = p.screenshot(return_img=True)
    p.close()
    return img


def render_preview(
    mesh_path,
    out_path=None,
    views: Sequence[str] = DEFAULT_VIEWS,
    size: int = 640,
    color: str = "#cfc4a7",
    separate: bool = False,
    show_grid: bool = True,
    title: Optional[str] = None,
):
    """Render *mesh_path* to a contact-sheet PNG. Returns the output path(s)."""
    import pyvista as pv
    import trimesh
    from PIL import Image, ImageDraw, ImageFont

    mesh_path = Path(mesh_path)
    tm = trimesh.load(str(mesh_path), force="mesh")
    if tm.is_empty:
        raise ValueError(f"No geometry in {mesh_path}")
    pd = pv.wrap(tm)
    bounds = pd.bounds  # (x0, x1, y0, y1, z0, z1)

    for v in views:
        if v not in VIEWS:
            raise ValueError(f"Unknown view '{v}'. Choose from: {', '.join(VIEWS)}")

    if out_path is None:
        out_path = mesh_path.with_name(mesh_path.stem + "_preview.png")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    images = {v: _render_view(pd, bounds, v, size, color, show_grid) for v in views}

    if separate:
        paths = []
        for v, img in images.items():
            pth = out_path.with_name(f"{out_path.stem}_{v}.png")
            Image.fromarray(img).save(pth)
            paths.append(pth)
        return paths

    # Contact sheet: header + labeled grid
    n = len(views)
    cols = 2 if n > 1 else 1
    rows = math.ceil(n / cols)
    header_h, label_h = 58, 26
    sheet = Image.new("RGB", (cols * size, header_h + rows * (size + label_h)), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 15)
        font_small = ImageFont.truetype("arial.ttf", 13)
    except OSError:
        font = font_small = ImageFont.load_default()

    ext = tm.extents
    line1 = title or mesh_path.name
    line2 = (
        f"{ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f} mm   |   "
        f"{len(tm.faces):,} tris   |   watertight: {'yes' if tm.is_watertight else 'NO'}"
    )
    draw.text((10, 8), line1, fill="black", font=font)
    draw.text((10, 30), line2, fill="#333333", font=font_small)

    for i, v in enumerate(views):
        cx = (i % cols) * size
        cy = header_h + (i // cols) * (size + label_h)
        draw.rectangle([cx, cy, cx + size, cy + label_h], fill="#e8e4d8")
        draw.text((cx + 8, cy + 5), v.upper(), fill="#444444", font=font_small)
        sheet.paste(Image.fromarray(images[v]), (cx, cy + label_h))

    sheet.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    import click

    @click.command("mesh-preview")
    @click.argument("mesh_file", type=click.Path(exists=True))
    @click.option("-o", "--output", default=None, type=click.Path(), help="Output PNG path")
    @click.option("--views", default=",".join(DEFAULT_VIEWS), help="Comma-separated view list")
    @click.option("--size", default=640, type=int, help="Pixels per view panel")
    @click.option("--color", default="#cfc4a7", help="Mesh color")
    @click.option("--separate", is_flag=True, help="Write one PNG per view instead of a sheet")
    @click.option("--no-grid", is_flag=True, help="Hide the dimension grid")
    def cli(mesh_file, output, views, size, color, separate, no_grid):
        """Render a mesh file to preview PNG(s)."""
        result = render_preview(
            mesh_file,
            out_path=output,
            views=[v.strip() for v in views.split(",") if v.strip()],
            size=size,
            color=color,
            separate=separate,
            show_grid=not no_grid,
        )
        if isinstance(result, list):
            for r in result:
                click.echo(f"wrote {r}")
        else:
            click.echo(f"wrote {result}")

    cli()


if __name__ == "__main__":
    main()
