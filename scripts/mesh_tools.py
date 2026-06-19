"""
Mesh tools - load/repair/edit operations on STL (and other) meshes
===================================================================
Library functions shared by ``edit_stl.py`` (CLI) and model scripts.
Built on trimesh; booleans use the manifold3d engine; hollowing and
last-resort repair go through a signed-distance voxel grid (robust on
messy, hand-made, or scanned meshes - at the cost of resampling detail).

All units mm.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import trimesh

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IO + info
# ---------------------------------------------------------------------------


def load_mesh(path) -> trimesh.Trimesh:
    m = trimesh.load(str(path), force="mesh")
    if m.is_empty:
        raise ValueError(f"No geometry in {path}")
    return m


def save_mesh(m: trimesh.Trimesh, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    m.export(str(path))
    return path


def mesh_info(m: trimesh.Trimesh) -> dict:
    ext = m.extents
    info = {
        "triangles": int(len(m.faces)),
        "vertices": int(len(m.vertices)),
        "watertight": bool(m.is_watertight),
        "winding_consistent": bool(m.is_winding_consistent),
        "components": int(m.body_count),
        "size_mm": [round(float(v), 3) for v in ext],
        "bounds_min": [round(float(v), 3) for v in m.bounds[0]],
        "bounds_max": [round(float(v), 3) for v in m.bounds[1]],
        "surface_area_mm2": round(float(m.area), 2),
    }
    try:
        info["volume_mm3"] = round(float(m.volume), 2)
    except Exception:
        info["volume_mm3"] = None
    return info


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------


def basic_repair(m: trimesh.Trimesh) -> trimesh.Trimesh:
    """Cheap, lossless-ish repair: merge/dedupe, fix winding, fill holes."""
    m = m.copy()
    m.process(validate=True)  # merge vertices, drop degenerate/duplicate faces
    trimesh.repair.fix_winding(m)
    trimesh.repair.fix_inversion(m, multibody=True)
    trimesh.repair.fix_normals(m, multibody=True)
    if not m.is_watertight:
        trimesh.repair.fill_holes(m)
    return m


def ensure_watertight(m: trimesh.Trimesh, voxel: Optional[float] = None) -> trimesh.Trimesh:
    """basic_repair, then voxel remesh as a last resort if still leaky."""
    fixed = basic_repair(m)
    if fixed.is_watertight:
        return fixed
    return voxel_remesh(fixed, voxel=voxel)


def _auto_voxel(m: trimesh.Trimesh) -> float:
    return float(np.clip(max(m.extents) / 220.0, 0.15, 1.0))


def _signed_grid(m: trimesh.Trimesh, voxel: float, pad: int = 4):
    """Signed-distance voxel grid (negative inside), and its world origin."""
    from scipy import ndimage

    est = np.prod(np.ceil(m.extents / voxel) + 2 * pad) * 8 / 1e6
    if est > 2000:
        raise MemoryError(
            f"Voxel grid at {voxel} mm would need ~{est:.0f} MB; use a larger --voxel."
        )
    vox = m.voxelized(pitch=voxel)
    origin = vox.indices_to_points(np.zeros((1, 3), dtype=int))[0]
    occ = vox.fill().matrix.astype(bool)
    occ = np.pad(occ, pad, mode="constant", constant_values=False)
    origin = origin - pad * voxel
    d_out = ndimage.distance_transform_edt(~occ)
    d_in = ndimage.distance_transform_edt(occ)
    grid = ((d_out - d_in) * voxel).astype(np.float32)
    return grid, origin


def _grid_to_mesh(grid: np.ndarray, origin, voxel: float, level: float = 0.0) -> trimesh.Trimesh:
    from skimage import measure

    verts, faces, _, _ = measure.marching_cubes(grid, level=level, spacing=(voxel,) * 3)
    out = trimesh.Trimesh(vertices=verts + origin, faces=faces, process=True)
    trimesh.repair.fix_normals(out)
    return out


def weld(m: trimesh.Trimesh, tolerance: float = 1e-3) -> trimesh.Trimesh:
    """Canonicalize through the Manifold kernel so watertightness survives
    the float32 STL round-trip (marching-cubes slivers, decimation seams).

    Falls back to :func:`basic_repair` if Manifold rejects the input.
    """
    import manifold3d as m3d

    mgl = m3d.Mesh(
        vert_properties=np.ascontiguousarray(m.vertices, dtype=np.float32),
        tri_verts=np.ascontiguousarray(m.faces, dtype=np.uint32),
        tolerance=tolerance,
    )
    mgl.merge()
    man = m3d.Manifold(mgl)
    if man.status() != m3d.Error.NoError:
        logger.warning("Manifold weld failed (status=%s); falling back to basic_repair", man.status())
        return basic_repair(m)
    out = man.to_mesh()
    verts = np.asarray(out.vert_properties)[:, :3]
    faces = np.asarray(out.tri_verts)
    fixed = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    trimesh.repair.fix_normals(fixed)
    return fixed


def voxel_remesh(m: trimesh.Trimesh, voxel: Optional[float] = None) -> trimesh.Trimesh:
    """Rebuild the mesh from a signed voxel grid. Always watertight.

    Heals self-intersections, holes, internal junk, and non-manifold mess.
    Resamples the surface, so crisp edges soften - pick *voxel* small
    enough for the detail you care about (default ~1/220 of the size).
    """
    voxel = voxel or _auto_voxel(m)
    grid, origin = _signed_grid(m, voxel)
    return _grid_to_mesh(grid, origin, voxel)


# ---------------------------------------------------------------------------
# Editing operations
# ---------------------------------------------------------------------------


def hollow(m: trimesh.Trimesh, wall: float = 2.0, voxel: Optional[float] = None) -> trimesh.Trimesh:
    """Hollow a solid leaving a *wall* mm shell (sealed internal cavity).

    Done in one marching-cubes pass on the signed grid:
    shell = { -wall <= distance <= 0 }. Remember sealed cavities trap
    resin/powder; boolean-subtract a drain hole afterwards if needed.
    """
    voxel = voxel or min(_auto_voxel(m), wall / 3.0)
    grid, origin = _signed_grid(m, voxel)
    shell_grid = np.maximum(grid, -(grid + np.float32(wall)))
    return _grid_to_mesh(shell_grid, origin, voxel)


def boolean_op(a: trimesh.Trimesh, b: trimesh.Trimesh, op: str) -> trimesh.Trimesh:
    """union / difference / intersection via the manifold engine."""
    if op not in ("union", "difference", "intersection"):
        raise ValueError(f"Unknown boolean op: {op}")
    result = trimesh.boolean.boolean_manifold([a, b], operation=op)
    if result.is_empty:
        raise ValueError(f"Boolean {op} produced empty geometry (parts not overlapping?)")
    return result


def scale_mesh(
    m: trimesh.Trimesh,
    factor: Optional[float] = None,
    to_x: Optional[float] = None,
    to_y: Optional[float] = None,
    to_z: Optional[float] = None,
    uniform: bool = True,
) -> trimesh.Trimesh:
    """Scale by a factor, or to hit an exact bounding-box dimension in mm."""
    m = m.copy()
    ext = m.extents
    targets = {0: to_x, 1: to_y, 2: to_z}
    given = {ax: t for ax, t in targets.items() if t is not None}
    if factor is not None:
        m.apply_scale(factor)
    elif given and uniform:
        ax, target = next(iter(given.items()))
        m.apply_scale(target / ext[ax])
    elif given:
        fac = [given.get(ax, ext[ax]) / ext[ax] for ax in range(3)]
        m.apply_scale(fac)
    else:
        raise ValueError("Provide factor or at least one of to_x/to_y/to_z")
    return m


def place_on_bed(m: trimesh.Trimesh, center_xy: bool = True) -> trimesh.Trimesh:
    """Translate so the part sits on Z=0, centered on the XY origin."""
    m = m.copy()
    lo, hi = m.bounds
    shift = [0.0, 0.0, -lo[2]]
    if center_xy:
        shift[0] = -(lo[0] + hi[0]) / 2
        shift[1] = -(lo[1] + hi[1]) / 2
    m.apply_translation(shift)
    return m


def rotate_mesh(m: trimesh.Trimesh, axis, angle_deg: float, about=None) -> trimesh.Trimesh:
    m = m.copy()
    about = m.bounds.mean(axis=0) if about is None else np.asarray(about, dtype=float)
    R = trimesh.transformations.rotation_matrix(np.radians(angle_deg), axis, about)
    m.apply_transform(R)
    return m


def slice_plane(m: trimesh.Trimesh, origin, normal, cap: bool = True) -> trimesh.Trimesh:
    """Keep the side of the cutting plane the *normal* points toward."""
    out = trimesh.intersections.slice_mesh_plane(
        m, plane_normal=np.asarray(normal, float), plane_origin=np.asarray(origin, float), cap=cap
    )
    if out is None or out.is_empty:
        raise ValueError("Plane cut removed the entire mesh")
    return out


def decimate(m: trimesh.Trimesh, target_faces: Optional[int] = None, ratio: Optional[float] = None) -> trimesh.Trimesh:
    """Reduce triangle count (quadric decimation)."""
    if target_faces is None:
        ratio = ratio or 0.5
        target_faces = max(int(len(m.faces) * ratio), 100)
    out = m.simplify_quadric_decimation(face_count=target_faces)
    out = weld(out)  # decimation leaves slivers that break watertightness
    return out


def smooth_mesh(m: trimesh.Trimesh, iterations: int = 10) -> trimesh.Trimesh:
    """Taubin smoothing (reduces voxel/scan ridges without much shrinkage)."""
    m = m.copy()
    trimesh.smoothing.filter_taubin(m, lamb=0.5, nu=-0.53, iterations=iterations)
    return weld(m) if m.is_watertight else basic_repair(m)
