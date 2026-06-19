"""
SDF Kit - Signed Distance Field modeling for organic, printable meshes
=======================================================================
Self-contained (numpy + scikit-image + trimesh) toolkit for building
organic shapes that OpenSCAD/CadQuery handle poorly: coral, antlers,
bones, blobby smooth-blended forms, noise-displaced surfaces.

Everything is a *distance function*: a callable ``f(points) -> distances``
where ``points`` is an (N, 3) float array and the result is (N,) -
negative inside the solid, positive outside. Compose functions, then call
:func:`mesh` to polygonize with marching cubes into a watertight
``trimesh.Trimesh``.

Units are millimeters. Z is up. Keep models sitting on Z=0.

Quick example::

    from scripts import sdf_kit as sk

    blob = sk.smooth_union(
        2.0,                       # blend radius (mm)
        sk.sphere(10),
        sk.sphere(8, center=(0, 0, 12)),
    )
    blob = sk.displace(blob, sk.fbm_noise(amplitude=0.6, frequency=0.15, seed=4))
    m = sk.mesh(blob, bounds=((-14, -14, -12), (14, 14, 24)), voxel=0.4)
    sk.save_stl(m, "blob.stl")

Design notes
------------
- Exact-ish SDF formulas follow Inigo Quilez's references.
- :func:`mesh` evaluates the field in cache-friendly 3D blocks, so SDFs
  that cull work per spatial chunk (see ``organic.skeleton_sdf``) stay fast.
- Marching cubes output is processed by trimesh: merged vertices,
  outward-consistent winding, optional small-component removal.
"""

from __future__ import annotations

import math
import time
from typing import Callable, Sequence

import numpy as np

SDF = Callable[[np.ndarray], np.ndarray]

_F = np.float32


# ---------------------------------------------------------------------------
# Small vector helpers
# ---------------------------------------------------------------------------


def _vec(v) -> np.ndarray:
    return np.asarray(v, dtype=_F)


def _length(a: np.ndarray, axis: int = -1) -> np.ndarray:
    return np.sqrt(np.sum(a * a, axis=axis))


def _rotation_matrix(axis, angle_deg: float) -> np.ndarray:
    """Rodrigues rotation matrix (3x3) for rotating points about *axis*."""
    axis = np.asarray(axis, dtype=np.float64)
    axis = axis / np.linalg.norm(axis)
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    x, y, z = axis
    K = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    R = np.eye(3) * c + s * K + (1 - c) * np.outer(axis, axis)
    return R.astype(_F)


# ---------------------------------------------------------------------------
# Primitives - each returns an SDF callable
# ---------------------------------------------------------------------------


def sphere(r: float, center=(0, 0, 0)) -> SDF:
    c = _vec(center)

    def f(p):
        return _length(p - c) - _F(r)

    return f


def box(size, center=(0, 0, 0)) -> SDF:
    """Axis-aligned box. *size* = full extents (sx, sy, sz)."""
    b = _vec(size) / 2
    c = _vec(center)

    def f(p):
        q = np.abs(p - c) - b
        outside = _length(np.maximum(q, 0))
        inside = np.minimum(np.max(q, axis=-1), 0)
        return outside + inside

    return f


def rounded_box(size, radius: float, center=(0, 0, 0)) -> SDF:
    """Box with all edges rounded by *radius* (outer size stays = size)."""
    inner = box(np.asarray(size, dtype=np.float64) - 2 * radius, center)
    return offset(inner, radius)


def cylinder(r: float, h: float, center=(0, 0, 0)) -> SDF:
    """Capped cylinder along Z. *h* = full height, centered on *center*."""
    c = _vec(center)
    r, hh = _F(r), _F(h / 2)

    def f(p):
        q = p - c
        dxy = np.sqrt(q[:, 0] ** 2 + q[:, 1] ** 2) - r
        dz = np.abs(q[:, 2]) - hh
        outside = np.sqrt(np.maximum(dxy, 0) ** 2 + np.maximum(dz, 0) ** 2)
        inside = np.minimum(np.maximum(dxy, dz), 0)
        return outside + inside

    return f


def capsule(p0, p1, r: float) -> SDF:
    """Sphere-swept line segment (round both ends)."""
    a, b = _vec(p0), _vec(p1)
    ab = b - a
    denom = _F(max(float(np.dot(ab, ab)), 1e-12))

    def f(p):
        pa = p - a
        h = np.clip((pa @ ab) / denom, 0.0, 1.0)
        return _length(pa - h[:, None] * ab) - _F(r)

    return f


def capped_cone(p0, p1, r0: float, r1: float) -> SDF:
    """Exact capped cone (flat ends) from p0 (radius r0) to p1 (radius r1)."""
    a, b = _vec(p0), _vec(p1)
    ba = b - a
    baba = _F(max(float(np.dot(ba, ba)), 1e-12))
    rba = _F(r1 - r0)
    r0f, r1f = _F(r0), _F(r1)
    k = rba * rba + baba

    def f(p):
        pa = p - a
        papa = np.sum(pa * pa, axis=-1)
        paba = (pa @ ba) / baba
        x = np.sqrt(np.maximum(papa - paba * paba * baba, 0))
        cax = np.maximum(0, x - np.where(paba < 0.5, r0f, r1f))
        cay = np.abs(paba - 0.5) - 0.5
        fclamp = np.clip((rba * (x - r0f) + paba * baba) / k, 0.0, 1.0)
        cbx = x - r0f - fclamp * rba
        cby = paba - fclamp
        s = np.where((cbx < 0) & (cay < 0), -1.0, 1.0).astype(_F)
        d2 = np.minimum(cax * cax + cay * cay * baba, cbx * cbx + cby * cby * baba)
        return s * np.sqrt(d2)

    return f


def cone_capsule(p0, p1, r0: float, r1: float) -> SDF:
    """Tapered segment with *round* ends (sphere-swept cone).

    The workhorse for branches/tubes: chains blend smoothly because the
    round ends overlap. Approximated as capsule with linearly
    interpolated radius (slightly thin for extreme tapers - fine here).
    """
    a, b = _vec(p0), _vec(p1)
    ab = b - a
    denom = _F(max(float(np.dot(ab, ab)), 1e-12))
    r0f, r1f = _F(r0), _F(r1)

    def f(p):
        pa = p - a
        h = np.clip((pa @ ab) / denom, 0.0, 1.0)
        r = r0f + (r1f - r0f) * h
        return _length(pa - h[:, None] * ab) - r

    return f


def torus(R: float, r: float, center=(0, 0, 0)) -> SDF:
    """Torus in the XY plane: major radius R, tube radius r."""
    c = _vec(center)

    def f(p):
        q = p - c
        qxy = np.sqrt(q[:, 0] ** 2 + q[:, 1] ** 2) - _F(R)
        return np.sqrt(qxy ** 2 + q[:, 2] ** 2) - _F(r)

    return f


def ellipsoid(radii, center=(0, 0, 0)) -> SDF:
    """Approximate ellipsoid SDF (good enough for meshing)."""
    rad = _vec(radii)
    c = _vec(center)

    def f(p):
        q = (p - c) / rad
        k0 = _length(q)
        k1 = _length(q / rad)
        return k0 * (k0 - 1.0) / np.maximum(k1, _F(1e-9))

    return f


def half_space(normal=(0, 0, 1), offset_d: float = 0.0) -> SDF:
    """Solid below the plane ``dot(p, n) = offset_d`` (n need not be unit)."""
    n = np.asarray(normal, dtype=np.float64)
    n = (n / np.linalg.norm(n)).astype(_F)

    def f(p):
        return (p @ n) - _F(offset_d)

    return f


def revolve_profile(profile_pts: Sequence[tuple], smooth_samples: int = 0) -> SDF:
    """Solid of revolution around the Z axis from a radius/height profile.

    *profile_pts*: ordered list of ``(radius, z)`` pairs from bottom to top,
    radius >= 0. The shape is closed flat at the first and last z.
    With ``smooth_samples > 0`` the profile is resampled through a
    Catmull-Rom spline for a smooth silhouette (e.g. 64).

    This is the precision tool for "exact silhouette" specs: intersect an
    organic interior with this envelope and the outer dimensions are exact.
    """
    pts = np.asarray(profile_pts, dtype=np.float64)
    if smooth_samples and len(pts) >= 3:
        pts = _catmull_rom(pts, smooth_samples)
        pts[:, 0] = np.maximum(pts[:, 0], 0.0)
    # Closed polygon in the (rho, z) half-plane: down the axis, out along
    # the bottom, up the profile, back along the top to the axis.
    poly = np.vstack(
        [
            [0.0, pts[0, 1]],
            pts,
            [0.0, pts[-1, 1]],
        ]
    ).astype(_F)
    vx, vy = poly[:, 0], poly[:, 1]
    n = len(poly)

    def f(p):
        rho = np.sqrt(p[:, 0] ** 2 + p[:, 1] ** 2)
        z = p[:, 2]
        d = (rho - vx[0]) ** 2 + (z - vy[0]) ** 2
        s = np.ones_like(rho)
        j = n - 1
        for i in range(n):
            ex, ey = vx[j] - vx[i], vy[j] - vy[i]
            wx, wy = rho - vx[i], z - vy[i]
            ee = max(ex * ex + ey * ey, 1e-12)
            t = np.clip((wx * ex + wy * ey) / ee, 0.0, 1.0)
            bx, by = wx - ex * t, wy - ey * t
            d = np.minimum(d, bx * bx + by * by)
            c1 = z >= vy[i]
            c2 = z < vy[j]
            c3 = ex * wy > ey * wx
            flip = (c1 & c2 & c3) | (~c1 & ~c2 & ~c3)
            s = np.where(flip, -s, s)
            j = i
        return s * np.sqrt(d)

    return f


def _catmull_rom(pts: np.ndarray, samples: int) -> np.ndarray:
    """Centripetal-ish Catmull-Rom resampling of a 2D/3D polyline."""
    pts = np.asarray(pts, dtype=np.float64)
    padded = np.vstack([pts[0], pts, pts[-1]])
    out = []
    n_seg = len(pts) - 1
    per = max(2, samples // max(n_seg, 1))
    for i in range(n_seg):
        p0, p1, p2, p3 = padded[i], padded[i + 1], padded[i + 2], padded[i + 3]
        t = np.linspace(0, 1, per, endpoint=(i == n_seg - 1))[:, None]
        out.append(
            0.5
            * (
                (2 * p1)
                + (-p0 + p2) * t
                + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3
            )
        )
    return np.vstack(out)


# ---------------------------------------------------------------------------
# Boolean ops (hard and smooth-blended)
# ---------------------------------------------------------------------------


def union(*fs: SDF) -> SDF:
    def f(p):
        d = fs[0](p)
        for g in fs[1:]:
            d = np.minimum(d, g(p))
        return d

    return f


def intersect(*fs: SDF) -> SDF:
    def f(p):
        d = fs[0](p)
        for g in fs[1:]:
            d = np.maximum(d, g(p))
        return d

    return f


def subtract(base: SDF, cutter: SDF) -> SDF:
    def f(p):
        return np.maximum(base(p), -cutter(p))

    return f


def intersect_pruned(outer: SDF, inner: SDF, margin: float = 2.0) -> SDF:
    """``intersect(outer, inner)`` where *inner* is only evaluated at points
    with ``outer < margin``. Big speedup when *outer* is a cheap envelope
    and *inner* is expensive (skeletons, noise stacks): everything outside
    the envelope skips the expensive field entirely.
    """

    def f(p):
        d = np.array(outer(p), copy=True)
        mask = d < margin
        if mask.any():
            d[mask] = np.maximum(d[mask], inner(p[mask]))
        return d

    return f


def _smin(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    """Polynomial smooth minimum (Quilez). k = blend distance in mm."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - _F(k) * h * (1.0 - h)


def smooth_union(k: float, *fs: SDF) -> SDF:
    """Union with fillet-like blending over distance *k* (mm)."""

    def f(p):
        d = fs[0](p)
        for g in fs[1:]:
            d = _smin(d, g(p), k)
        return d

    return f


def smooth_intersect(k: float, *fs: SDF) -> SDF:
    def f(p):
        d = fs[0](p)
        for g in fs[1:]:
            d = -_smin(-d, -g(p), k)
        return d

    return f


def smooth_subtract(k: float, base: SDF, cutter: SDF) -> SDF:
    def f(p):
        return -_smin(-base(p), cutter(p), k)

    return f


# ---------------------------------------------------------------------------
# Modifiers
# ---------------------------------------------------------------------------


def translate(f: SDF, v) -> SDF:
    vv = _vec(v)
    return lambda p: f(p - vv)


def rotate(f: SDF, axis, angle_deg: float) -> SDF:
    """Rotate the *object* about an axis through the origin."""
    Rinv = _rotation_matrix(axis, -angle_deg)
    return lambda p: f(p @ Rinv.T)


def scale(f: SDF, s: float) -> SDF:
    """Uniform scale (non-uniform scaling breaks distance metrics)."""
    s = float(s)
    return lambda p: f(p / _F(s)) * _F(s)


def offset(f: SDF, d: float) -> SDF:
    """Dilate (d>0) or erode (d<0) the surface."""
    return lambda p: f(p) - _F(d)


def shell(f: SDF, thickness: float) -> SDF:
    """Hollow shell of the surface, *thickness* mm thick (centered)."""
    t = _F(thickness / 2)
    return lambda p: np.abs(f(p)) - t


def displace(f: SDF, g: Callable[[np.ndarray], np.ndarray]) -> SDF:
    """Add a scalar field to the distance (surface texture/noise).

    Keep |g| smaller than real features and use a voxel size finer than
    the displacement amplitude.
    """
    return lambda p: f(p) + g(p)


def twist(f: SDF, degrees_per_mm: float) -> SDF:
    """Twist around the Z axis as height increases."""
    rate = math.radians(degrees_per_mm)

    def w(p):
        a = p[:, 2] * _F(rate)
        c, s = np.cos(a), np.sin(a)
        q = np.empty_like(p)
        q[:, 0] = c * p[:, 0] + s * p[:, 1]
        q[:, 1] = -s * p[:, 0] + c * p[:, 1]
        q[:, 2] = p[:, 2]
        return f(q)

    return w


def warp(f: SDF, amplitude: float, frequency: float = 0.04, octaves: int = 2, seed: int = 0) -> SDF:
    """Domain-warp: bend space with low-frequency vector noise before
    evaluating *f*. Straight edges and struts turn gently wavy/organic
    (use on lattices, ribs, anything too CAD-perfect).

    Keep *amplitude* modest (1-4 mm) and *frequency* low (0.02-0.08):
    the warp bends the distance metric too, so big values distort
    thicknesses. Flat reference faces (a build-plate bottom, a rim you
    union on afterwards) should NOT be warped - warp the organic part,
    then add the precise parts.
    """
    gx = fbm_noise(amplitude, frequency, octaves, seed=seed)
    gy = fbm_noise(amplitude, frequency, octaves, seed=seed + 101)
    gz = fbm_noise(amplitude, frequency, octaves, seed=seed + 202)

    def w(p):
        q = np.array(p, copy=True)
        q[:, 0] += gx(p)
        q[:, 1] += gy(p)
        q[:, 2] += gz(p)
        return f(q)

    return w


def repeat_polar(f: SDF, count: int) -> SDF:
    """Repeat the geometry *count* times around the Z axis.

    Model one wedge centered on the +X axis; it is mirrored into all
    sectors. Slight distance distortion at sector seams is normal.
    """
    sector = 2 * math.pi / count

    def w(p):
        ang = np.arctan2(p[:, 1], p[:, 0])
        rad = np.sqrt(p[:, 0] ** 2 + p[:, 1] ** 2)
        a = np.mod(ang + sector / 2, sector) - sector / 2
        q = np.empty_like(p)
        q[:, 0] = rad * np.cos(a)
        q[:, 1] = rad * np.sin(a)
        q[:, 2] = p[:, 2]
        return f(q)

    return w


def mirror_x(f: SDF) -> SDF:
    return lambda p: f(np.column_stack([np.abs(p[:, 0]), p[:, 1], p[:, 2]]))


# ---------------------------------------------------------------------------
# Deterministic value noise (no external deps, seeded, vectorized)
# ---------------------------------------------------------------------------


def _hash3(ix, iy, iz, seed: int):
    h = (
        ix.astype(np.uint32) * np.uint32(0x9E3779B1)
        ^ iy.astype(np.uint32) * np.uint32(0x85EBCA77)
        ^ iz.astype(np.uint32) * np.uint32(0xC2B2AE3D)
        ^ np.uint32((seed * 0x27D4EB2F + 0x165667B1) & 0xFFFFFFFF)
    )
    h ^= h >> np.uint32(15)
    h *= np.uint32(0x2C1B3C6D)
    h ^= h >> np.uint32(12)
    h *= np.uint32(0x297A2D39)
    h ^= h >> np.uint32(15)
    return h.astype(np.float64) / 4294967296.0  # [0, 1)


def _value_noise(p: np.ndarray, seed: int) -> np.ndarray:
    """Trilinear value noise on the unit lattice, output roughly [-1, 1]."""
    pf = np.floor(p)
    ix, iy, iz = (pf[:, 0].astype(np.int64), pf[:, 1].astype(np.int64), pf[:, 2].astype(np.int64))
    fx, fy, fz = (p[:, 0] - pf[:, 0], p[:, 1] - pf[:, 1], p[:, 2] - pf[:, 2])
    # Quintic fade for smooth derivatives
    ux = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
    uy = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
    uz = fz * fz * fz * (fz * (fz * 6 - 15) + 10)

    def corner(dx, dy, dz):
        return _hash3(ix + dx, iy + dy, iz + dz, seed)

    c000, c100 = corner(0, 0, 0), corner(1, 0, 0)
    c010, c110 = corner(0, 1, 0), corner(1, 1, 0)
    c001, c101 = corner(0, 0, 1), corner(1, 0, 1)
    c011, c111 = corner(0, 1, 1), corner(1, 1, 1)
    x00 = c000 + (c100 - c000) * ux
    x10 = c010 + (c110 - c010) * ux
    x01 = c001 + (c101 - c001) * ux
    x11 = c011 + (c111 - c011) * ux
    y0 = x00 + (x10 - x00) * uy
    y1 = x01 + (x11 - x01) * uy
    v = y0 + (y1 - y0) * uz
    return (v * 2.0 - 1.0).astype(_F)


def fbm_noise(
    amplitude: float = 1.0,
    frequency: float = 0.1,
    octaves: int = 3,
    lacunarity: float = 2.0,
    gain: float = 0.5,
    seed: int = 0,
) -> Callable[[np.ndarray], np.ndarray]:
    """Fractal value-noise scalar field for :func:`displace`.

    *frequency* is cycles per mm (0.05-0.2 = broad lumps, 0.5+ = fine
    grain). Output amplitude is roughly +/-*amplitude* mm. Deterministic
    for a given seed.
    """

    def g(p):
        total = np.zeros(len(p), dtype=_F)
        amp, freq = 1.0, frequency
        norm = 0.0
        for o in range(octaves):
            total += amp * _value_noise(p * _F(freq), seed + o * 1013)
            norm += amp
            amp *= gain
            freq *= lacunarity
        return (total / norm * _F(amplitude)).astype(_F)

    return g


# ---------------------------------------------------------------------------
# Meshing - SDF -> watertight trimesh via marching cubes
# ---------------------------------------------------------------------------


def mesh(
    f: SDF,
    bounds,
    voxel: float = 0.5,
    block: int = 48,
    keep: str = "largest",
    min_component_volume: float = 1.0,
    decimate_to: int | None = None,
    verbose: bool = True,
):
    """Polygonize an SDF into a watertight ``trimesh.Trimesh``.

    Parameters
    ----------
    f : SDF
        The distance function.
    bounds : ((x0,y0,z0), (x1,y1,z1))
        Evaluation box in mm. Make it ~2 voxels larger than the model on
        every side; geometry crossing the boundary is capped flat.
    voxel : float
        Grid resolution in mm. 0.4-0.8 is right for most prints
        (smaller = finer surface, more RAM/time, bigger STL).
    block : int
        Evaluation chunk edge length in voxels. Spatially-coherent
        chunks let culling SDFs skip far geometry.
    keep : 'all' | 'largest' | 'big'
        'largest' keeps only the biggest connected component,
        'big' keeps components above *min_component_volume* (mm^3),
        'all' keeps everything (floating debris and all).
    decimate_to : int | None
        Target triangle count (e.g. 250_000). Marching cubes over-
        tessellates; decimating organic shapes is visually lossless.

    The result is welded through the Manifold kernel, so watertightness
    survives STL export/reload.
    """
    import trimesh
    from skimage import measure

    lo = np.asarray(bounds[0], dtype=np.float64)
    hi = np.asarray(bounds[1], dtype=np.float64)
    if not np.all(lo < hi):
        raise ValueError(
            f"bounds lo must be < hi in every axis; got lo={tuple(lo)}, hi={tuple(hi)}"
        )
    dims = np.maximum(np.ceil((hi - lo) / voxel).astype(int) + 1, 2)
    nx, ny, nz = (int(dims[0]), int(dims[1]), int(dims[2]))
    n_total = nx * ny * nz
    est_mb = n_total * 4 / 1e6
    if verbose:
        print(f"[sdf_kit] grid {nx}x{ny}x{nz} = {n_total:,} voxels (~{est_mb:.0f} MB) @ {voxel} mm")
    if est_mb > 1500:
        raise MemoryError(
            f"Voxel grid would need ~{est_mb:.0f} MB. Increase `voxel` "
            f"(currently {voxel}) or shrink `bounds`."
        )

    xs = (lo[0] + np.arange(nx) * voxel).astype(_F)
    ys = (lo[1] + np.arange(ny) * voxel).astype(_F)
    zs = (lo[2] + np.arange(nz) * voxel).astype(_F)
    volume = np.empty((nx, ny, nz), dtype=_F)

    t0 = time.perf_counter()
    for bx in range(0, nx, block):
        ex = min(bx + block, nx)
        for by in range(0, ny, block):
            ey = min(by + block, ny)
            for bz in range(0, nz, block):
                ez = min(bz + block, nz)
                X, Y, Z = np.meshgrid(xs[bx:ex], ys[by:ey], zs[bz:ez], indexing="ij")
                pts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
                volume[bx:ex, by:ey, bz:ez] = np.asarray(f(pts), dtype=_F).reshape(X.shape)
    t_eval = time.perf_counter() - t0

    # Cap anything crossing the boundary so the mesh stays closed.
    border = _F(max(voxel, 1e-3))
    volume[0, :, :] = np.maximum(volume[0, :, :], border)
    volume[-1, :, :] = np.maximum(volume[-1, :, :], border)
    volume[:, 0, :] = np.maximum(volume[:, 0, :], border)
    volume[:, -1, :] = np.maximum(volume[:, -1, :], border)
    volume[:, :, 0] = np.maximum(volume[:, :, 0], border)
    volume[:, :, -1] = np.maximum(volume[:, :, -1], border)

    if volume.min() >= 0:
        raise ValueError(
            "SDF is positive everywhere in bounds - no surface found. "
            "Check bounds placement and units."
        )

    # Samples exactly on the surface (e.g. a half_space bottom landing on a
    # grid plane) make marching cubes emit degenerate triangles that defeat
    # welding; nudge them a hair inside so every crossing is unambiguous.
    volume[volume == 0] = _F(-1e-5)

    t0 = time.perf_counter()
    verts, faces, _normals, _vals = measure.marching_cubes(volume, level=0.0, spacing=(voxel, voxel, voxel))
    verts = verts + lo
    t_mc = time.perf_counter() - t0

    m = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    trimesh.repair.fix_normals(m)

    if keep != "all":
        parts = m.split(only_watertight=False)
        if len(parts) > 1:
            for part in parts:
                trimesh.repair.fix_normals(part)
            if keep == "largest":
                parts = sorted(parts, key=lambda x: abs(x.volume), reverse=True)[:1]
            else:  # 'big'
                parts = [q for q in parts if abs(q.volume) >= min_component_volume] or [
                    max(parts, key=lambda x: abs(x.volume))
                ]
            m = trimesh.util.concatenate(parts) if len(parts) > 1 else parts[0]

    if decimate_to and len(m.faces) > decimate_to:
        m = m.simplify_quadric_decimation(face_count=decimate_to)

    # Weld so watertightness survives the float32 STL round-trip.
    from scripts.mesh_tools import weld

    m = weld(m)

    if verbose:
        bb = m.bounds
        size = bb[1] - bb[0]
        print(
            f"[sdf_kit] eval {t_eval:.1f}s, marching cubes {t_mc:.1f}s -> "
            f"{len(m.faces):,} tris, bbox {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm, "
            f"watertight={m.is_watertight}"
        )
    return m


def save_stl(m, path, verbose: bool = True) -> None:
    """Export a mesh as binary STL, creating parent dirs."""
    from pathlib import Path

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    m.export(str(path))
    if verbose:
        print(f"[sdf_kit] wrote {path} ({path.stat().st_size / 1e6:.2f} MB)")
