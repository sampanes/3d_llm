"""
Organic growth helpers - skeletons, branches, tube clusters, envelopes
======================================================================
Builds on :mod:`scripts.sdf_kit`. The core idea: organic forms are
*skeletons* (chains of tapered segments) smooth-blended into one solid,
optionally intersected with an exact-dimension *envelope* so the
silhouette hits the numbers in the spec even though the interior is
grown procedurally.

Typical recipes
---------------
Antler / branching coral::

    skel = grow_branches(length=90, radius=7, levels=4, splits=(2, 3),
                         split_angle=38, up_bias=0.25, seed=11)
    f = skeleton_sdf(skel, blend=2.5)

Organ-pipe coral with an exact base/top/height::

    prof, r_of_z = taper_profile(base_r=45, top_r=18, height=140, curve=1.2)
    skel = organ_pipe_tubes(count=40, base_disk_r=38, height=140,
                            radial_scale=lambda z: r_of_z(z) / r_of_z(0))
    f = sk.intersect(skeleton_sdf(skel, blend=2.0),
                     sk.revolve_profile(prof))

Voronoi lattice shell (the open-cell printed vase/lamp look)::

    prof = [(34, 0), (46, 20), (40, 60), (54, 140), (74, 160)]  # (radius, z)
    seeds = surface_points(prof, count=180, smooth_samples=96, seed=5)
    f = voronoi_lattice(seeds, revolved_sheet(prof, smooth_samples=96),
                        strut_r=1.6)

All units mm, Z up, models grow from z=0.
"""

from __future__ import annotations

import math
from typing import Callable, Optional, Sequence

import numpy as np

from scripts import sdf_kit as sk

_F = np.float32
GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))  # ~137.5 deg


# ---------------------------------------------------------------------------
# Skeleton: a bag of tapered segments
# ---------------------------------------------------------------------------


class Skeleton:
    """Tapered line segments: a[i] -> b[i] with radii r0[i] -> r1[i]."""

    def __init__(self):
        self._a: list = []
        self._b: list = []
        self._r0: list = []
        self._r1: list = []
        # Generators may record branch/tube endpoints here as
        # (position ndarray(3,), tip_radius) - used e.g. to carve tube mouths.
        self.tips: list = []

    def add(self, p0, p1, r0: float, r1: float) -> None:
        self._a.append(np.asarray(p0, dtype=np.float64))
        self._b.append(np.asarray(p1, dtype=np.float64))
        self._r0.append(float(r0))
        self._r1.append(float(r1))

    def add_path(self, points: np.ndarray, r_start: float, r_end: float) -> None:
        """Add a polyline as a chain of segments with linear radius taper."""
        points = np.asarray(points, dtype=np.float64)
        n = len(points) - 1
        if n < 1:
            return
        # Taper by arc length so kinked paths don't bunch the taper
        seglen = np.linalg.norm(np.diff(points, axis=0), axis=1)
        cum = np.concatenate([[0.0], np.cumsum(seglen)])
        total = max(cum[-1], 1e-9)
        for i in range(n):
            t0, t1 = cum[i] / total, cum[i + 1] / total
            self.add(
                points[i],
                points[i + 1],
                r_start + (r_end - r_start) * t0,
                r_start + (r_end - r_start) * t1,
            )

    def extend(self, other: "Skeleton") -> None:
        self._a.extend(other._a)
        self._b.extend(other._b)
        self._r0.extend(other._r0)
        self._r1.extend(other._r1)

    def __len__(self) -> int:
        return len(self._a)

    def arrays(self):
        A = np.asarray(self._a, dtype=_F)
        B = np.asarray(self._b, dtype=_F)
        R0 = np.asarray(self._r0, dtype=_F)
        R1 = np.asarray(self._r1, dtype=_F)
        return A, B, R0, R1

    def bounds(self, margin: float = 0.0):
        """Axis-aligned bounds of the skeleton including radii (+margin)."""
        A, B, R0, R1 = self.arrays()
        r = np.maximum(R0, R1)[:, None]
        lo = np.minimum(A - r, B - r).min(axis=0) - margin
        hi = np.maximum(A + r, B + r).max(axis=0) + margin
        return lo, hi


def skeleton_sdf(skel: Skeleton, blend: float = 2.0, cull_pad: float = 3.0) -> sk.SDF:
    """Smooth-blended solid around all segments of a skeleton.

    *blend* (mm) controls how much joints and neighbors melt together
    (2-4 looks fleshy/coral-like; 0.5-1 keeps tubes crisp).

    The returned SDF culls segments per evaluation chunk (the chunks come
    from ``sdf_kit.mesh``'s block evaluation), so hundreds of segments
    stay tractable. *cull_pad* is extra safety margin in mm - raise it if
    you ever see chunk-shaped artifacts (you shouldn't).
    """
    if len(skel) == 0:
        raise ValueError("Skeleton is empty")
    A, B, R0, R1 = skel.arrays()
    AB = B - A
    denom = np.maximum(np.einsum("ij,ij->i", AB, AB), 1e-12).astype(_F)
    Rmax = np.maximum(R0, R1)
    seglen = np.sqrt(denom)
    MID = (A + B) / 2
    k = float(blend)

    def f(p: np.ndarray) -> np.ndarray:
        lo = p.min(axis=0)
        hi = p.max(axis=0)
        half_diag = float(np.linalg.norm(hi - lo)) / 2

        def d_box(pts):  # point-to-chunk-AABB distance, vectorized
            dv = np.maximum(np.maximum(lo[None, :] - pts, pts - hi[None, :]), 0.0)
            return np.sqrt(np.sum(dv * dv, axis=1))

        # Lower bound on each segment's distance to any point in the chunk:
        # sample 3 points along the segment (error <= seglen/4).
        L = np.minimum(np.minimum(d_box(A), d_box(B)), d_box(MID)) - seglen / 4 - Rmax

        # Upper bound on the chunk's min distance to the nearest segment:
        # exact distance from chunk center to that segment.
        c = ((lo + hi) / 2)[None, :]
        pa = c - A
        h = np.clip(np.einsum("ij,ij->i", pa, AB) / denom, 0.0, 1.0)
        d_center = np.linalg.norm(pa - h[:, None] * AB, axis=1) - Rmax
        U = float(d_center.min()) + half_diag

        L_min = float(L.min())
        far = 2 * k + cull_pad
        if L_min > far:
            # Whole chunk is far from every segment: positive everywhere.
            return np.full(len(p), max(L_min, far), dtype=_F)

        keep = np.nonzero(L <= U + 2 * k + cull_pad)[0]
        d = None
        for i in keep:
            pa_i = p - A[i]
            h_i = np.clip((pa_i @ AB[i]) / denom[i], 0.0, 1.0)
            r_i = R0[i] + (R1[i] - R0[i]) * h_i
            d_i = np.sqrt(np.sum((pa_i - h_i[:, None] * AB[i]) ** 2, axis=1)) - r_i
            d = d_i if d is None else sk._smin(d, d_i, k)
        return d

    return f


# ---------------------------------------------------------------------------
# Placement + profiles
# ---------------------------------------------------------------------------


def phyllotaxis_disk(count: int, radius: float, jitter: float = 0.0, seed: int = 0) -> np.ndarray:
    """(count, 2) sunflower-spiral points evenly filling a disk."""
    rng = np.random.default_rng(seed)
    i = np.arange(count) + 0.5
    r = radius * np.sqrt(i / count)
    th = i * GOLDEN_ANGLE
    pts = np.column_stack([r * np.cos(th), r * np.sin(th)])
    if jitter > 0:
        pts += rng.normal(0, jitter, pts.shape)
    return pts


def taper_profile(
    base_r: float,
    top_r: float,
    height: float,
    curve: float = 0.0,
    points: int = 33,
):
    """Radius-vs-height profile from an exact base radius to an exact top.

    curve = 0   straight-sided (conical)
    curve > 0   concave - narrows fast near the base, eases toward the top
    curve < 0   convex - bulges outward before narrowing

    Returns ``(profile_pts, radius_of_z)``:
    - *profile_pts*: list of (radius, z) for :func:`sdf_kit.revolve_profile`
    - *radius_of_z*: callable mapping z (mm) -> profile radius (mm)
    """
    t = np.linspace(0.0, 1.0, points)
    if abs(curve) < 1e-9:
        shape = t
    else:
        shape = (np.exp(curve * t) - 1.0) / (np.exp(curve) - 1.0)
    r = base_r + (top_r - base_r) * shape
    z = t * height
    prof = list(zip(r.tolist(), z.tolist()))

    def radius_of_z(zq):
        return np.interp(zq, z, r)

    return prof, radius_of_z


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


def organ_pipe_tubes(
    count: int = 36,
    base_disk_r: float = 36.0,
    height: float = 140.0,
    min_height_frac: float = 0.5,
    tube_r: tuple = (3.2, 6.0),
    taper: float = 0.85,
    radial_scale: Optional[Callable[[float], float]] = None,
    wander: float = 2.0,
    steps: int = 12,
    center_tall: bool = True,
    seed: int = 0,
) -> Skeleton:
    """Cluster of near-vertical tubes rising from a disk (organ-pipe coral).

    Parameters
    ----------
    count, base_disk_r
        How many tubes and the radius of the placement disk at z=0.
    height
        Height of the tallest tube tops (mm).
    min_height_frac
        Shortest tubes as a fraction of *height*.
    tube_r
        (min, max) tube radius; assigned per tube, thicker toward center.
    taper
        Tip radius as a fraction of that tube's base radius.
    radial_scale
        Callable z -> scale factor applied to each tube's XY position, used
        to pull the cluster inward as it rises (pass the normalized envelope
        profile). None = straight up.
    wander
        Lateral random-walk amplitude in mm over a tube's full height.
    center_tall
        Taller tubes near the middle (classic organ/coral look).
    """
    rng = np.random.default_rng(seed)
    xy = phyllotaxis_disk(count, base_disk_r, jitter=base_disk_r * 0.02, seed=seed + 1)
    rel = np.linalg.norm(xy, axis=1) / max(base_disk_r, 1e-9)

    skel = Skeleton()
    for i in range(count):
        if center_tall:
            hfrac = 1.0 - (rel[i] ** 1.4) * (1.0 - min_height_frac)
        else:
            hfrac = 1.0 - rng.uniform(0, 1.0 - min_height_frac)
        hfrac *= rng.uniform(0.97, 1.0)
        h = height * hfrac

        r_base = tube_r[1] - (tube_r[1] - tube_r[0]) * rel[i] * rng.uniform(0.7, 1.0)

        z = np.linspace(0.0, h, steps + 1)
        # Smooth lateral wander: integrated random steps, pinned at the base
        drift = np.cumsum(rng.normal(0, 1.0, (steps + 1, 2)), axis=0)
        drift -= drift[0]
        scale_w = wander / max(np.abs(drift).max(), 1e-9)
        path = np.empty((steps + 1, 3))
        for j, zj in enumerate(z):
            s = radial_scale(zj) if radial_scale is not None else 1.0
            path[j, 0] = xy[i, 0] * s + drift[j, 0] * scale_w
            path[j, 1] = xy[i, 1] * s + drift[j, 1] * scale_w
            path[j, 2] = zj
        skel.add_path(path, r_base, r_base * taper)
        skel.tips.append((path[-1].copy(), r_base * taper))
    return skel


def grow_branches(
    origin=(0.0, 0.0, 0.0),
    direction=(0.0, 0.0, 1.0),
    length: float = 80.0,
    radius: float = 7.0,
    levels: int = 4,
    splits: tuple = (2, 3),
    split_angle: float = 35.0,
    azimuth_jitter: float = 25.0,
    length_decay: float = 0.72,
    radius_decay: float = 0.65,
    steps_per_branch: int = 6,
    wander: float = 10.0,
    up_bias: float = 0.15,
    min_radius: float = 0.8,
    seed: int = 0,
    max_segments: int = 6000,
) -> Skeleton:
    """Recursive branching skeleton - antlers, trees, branching coral.

    Each branch is a curved chain of *steps_per_branch* segments; at its
    tip it splits into ``randint(*splits)`` children rotated away from
    the parent direction by *split_angle* (deg) at jittered azimuths.

    Key dials
    ---------
    wander        per-step random bend in degrees (gnarliness)
    up_bias       0..1 pull toward +Z (phototropism); negative droops
    radius_decay  child base radius = parent tip radius * this
    min_radius    stop splitting below this (printability floor ~0.8mm)
    """
    rng = np.random.default_rng(seed)
    skel = Skeleton()

    def _unit(v):
        n = np.linalg.norm(v)
        return v / n if n > 1e-12 else np.array([0.0, 0.0, 1.0])

    def _perp(v):
        ref = np.array([1.0, 0.0, 0.0]) if abs(v[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        return _unit(np.cross(v, ref))

    def _rotated(v, axis, deg):
        R = sk._rotation_matrix(axis, deg)
        return _unit(R @ v)

    def grow(pos, dirv, blen, brad, level):
        if len(skel) >= max_segments:
            return
        tip_r = max(brad * radius_decay, min_radius * 0.75)
        step = blen / steps_per_branch
        pts = [np.asarray(pos, dtype=np.float64)]
        d = _unit(np.asarray(dirv, dtype=np.float64))
        for _ in range(steps_per_branch):
            # Random bend + upward pull, renormalized each step
            bend_axis = _perp(d + rng.normal(0, 0.3, 3))
            d = _rotated(d, bend_axis, rng.normal(0, wander))
            d = _unit(d + np.array([0.0, 0.0, up_bias]))
            pts.append(pts[-1] + d * step)
        skel.add_path(np.asarray(pts), brad, tip_r)

        if level <= 1 or tip_r <= min_radius:
            skel.tips.append((pts[-1].copy(), tip_r))
            return
        n_children = int(rng.integers(splits[0], splits[1] + 1))
        base_az = rng.uniform(0, 360)
        for ci in range(n_children):
            az = base_az + 360.0 * ci / n_children + rng.normal(0, azimuth_jitter)
            tilt = split_angle * rng.uniform(0.75, 1.25)
            child_dir = _rotated(d, _perp(d), tilt)
            child_dir = _rotated(child_dir, d, az)
            grow(
                pts[-1],
                child_dir,
                blen * length_decay * rng.uniform(0.85, 1.15),
                tip_r,
                level - 1,
            )

    grow(np.asarray(origin, dtype=np.float64), direction, length, radius, levels)
    return skel


# ---------------------------------------------------------------------------
# Voronoi lattice shells - open polygonal-cell strut networks on a surface
# ---------------------------------------------------------------------------


def _resample_profile(profile_pts, smooth_samples: int) -> np.ndarray:
    """(radius, z) polyline, optionally Catmull-Rom smoothed, radii >= 0."""
    pts = np.asarray(profile_pts, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 2 or len(pts) < 2:
        raise ValueError("profile_pts must be a list of (radius, z) pairs")
    if smooth_samples and len(pts) >= 3:
        pts = sk._catmull_rom(pts, smooth_samples)
        pts[:, 0] = np.maximum(pts[:, 0], 0.0)
    return pts


def revolved_sheet(profile_pts: Sequence[tuple], smooth_samples: int = 0) -> sk.SDF:
    """UNSIGNED distance to the open surface swept by revolving a
    (radius, z) profile polyline around the Z axis.

    Unlike :func:`sdf_kit.revolve_profile` (a *closed solid* with flat top
    and bottom caps), this is just the lateral sheet - no caps, no inside.
    The field is zero exactly on the sheet and positive everywhere else,
    which is what surface-following tools like :func:`voronoi_lattice`
    need. Not a solid: meshing it directly produces nothing.
    """
    pts = _resample_profile(profile_pts, smooth_samples)
    vx = pts[:, 0].astype(_F)
    vz = pts[:, 1].astype(_F)
    ex = np.diff(vx)
    ez = np.diff(vz)
    ee = np.maximum(ex * ex + ez * ez, _F(1e-12))
    nseg = len(ex)

    def f(p):
        rho = np.sqrt(p[:, 0] ** 2 + p[:, 1] ** 2)
        z = p[:, 2]
        d2 = None
        for i in range(nseg):
            wx = rho - vx[i]
            wz = z - vz[i]
            t = np.clip((wx * ex[i] + wz * ez[i]) / ee[i], 0.0, 1.0)
            bx = wx - ex[i] * t
            bz = wz - ez[i] * t
            di = bx * bx + bz * bz
            d2 = di if d2 is None else np.minimum(d2, di)
        return np.sqrt(d2)

    return f


def surface_points(
    profile_pts: Sequence[tuple],
    count: int,
    smooth_samples: int = 0,
    relax_iters: int = 6,
    relax_step: float = 0.3,
    density: Optional[Callable[[float, float], float]] = None,
    seed: int = 0,
) -> np.ndarray:
    """Roughly even ("blue noise") points on a surface of revolution.

    Same (radius, z) profile convention as :func:`revolved_sheet`. Points
    are scattered area-weighted along the profile, then *relax_iters*
    rounds of neighbor repulsion (re-projected onto the surface each
    round) spread them out evenly while keeping organic irregularity.
    Feed the result to :func:`voronoi_lattice` as cell seeds.

    relax_iters 0 = pure random (very uneven cells), 4-8 = natural,
    15+ = almost regular honeycomb. *density* is an optional
    ``(radius, z) -> relative weight`` callable for cell-size gradients
    (e.g. ``lambda r, z: 2.0 - z / H`` = small cells low, big cells
    high). Deterministic per seed.
    """
    from scipy.spatial import cKDTree

    if count < 4:
        raise ValueError("count must be >= 4")
    rng = np.random.default_rng(seed)
    pts = _resample_profile(profile_pts, smooth_samples)
    seg = np.diff(pts, axis=0)
    seglen = np.hypot(seg[:, 0], seg[:, 1])
    ee = np.maximum(seglen * seglen, 1e-12)
    # Lateral area of each profile segment ~ mean radius * length
    area_w = np.maximum((pts[:-1, 0] + pts[1:, 0]) * 0.5 * seglen, 1e-12)
    spacing = math.sqrt(2 * math.pi * float(area_w.sum()) / count)
    if density is not None:
        mid = (pts[:-1] + pts[1:]) * 0.5
        area_w = area_w * np.maximum(
            [float(density(r, z)) for r, z in mid], 1e-6
        )
    cdf = np.concatenate([[0.0], np.cumsum(area_w)])

    u = rng.random(count) * cdf[-1]
    i = np.clip(np.searchsorted(cdf, u) - 1, 0, len(seglen) - 1)
    t = (u - cdf[i]) / area_w[i]
    r = pts[i, 0] + seg[i, 0] * t
    z = pts[i, 1] + seg[i, 1] * t
    phi = rng.uniform(0.0, 2 * math.pi, count)
    P = np.column_stack([r * np.cos(phi), r * np.sin(phi), z])

    def project(P):
        """Snap each point to the nearest spot on the revolved profile."""
        rho = np.maximum(np.hypot(P[:, 0], P[:, 1]), 1e-9)
        z = P[:, 2]
        best_d2 = np.full(len(P), np.inf)
        best_r = np.empty(len(P))
        best_z = np.empty(len(P))
        for j in range(len(seglen)):
            wr = rho - pts[j, 0]
            wz = z - pts[j, 1]
            tt = np.clip((wr * seg[j, 0] + wz * seg[j, 1]) / ee[j], 0.0, 1.0)
            pr = pts[j, 0] + seg[j, 0] * tt
            pz = pts[j, 1] + seg[j, 1] * tt
            d2 = (rho - pr) ** 2 + (z - pz) ** 2
            better = d2 < best_d2
            best_d2[better] = d2[better]
            best_r[better] = pr[better]
            best_z[better] = pz[better]
        s = best_r / rho
        return np.column_stack([P[:, 0] * s, P[:, 1] * s, best_z])

    P = project(P)
    k = min(7, count)
    for _ in range(max(0, relax_iters)):
        tree = cKDTree(P)
        d, nb = tree.query(P, k=k)
        d, nb = d[:, 1:], nb[:, 1:]
        diff = P[:, None, :] - P[nb]
        dn = np.maximum(d, 1e-9)[..., None]
        wgt = np.maximum(0.0, 1.0 - d / (1.7 * spacing))[..., None]
        P = P + relax_step * spacing * (diff / dn * wgt).mean(axis=1)
        P = project(P)
    return P


def voronoi_lattice(
    points: np.ndarray,
    sheet: sk.SDF,
    strut_r: float = 1.6,
    workers: int = -1,
) -> sk.SDF:
    """Round-strut Voronoi web lying on a surface - the classic printed
    "voronoi shell" look: open polygonal cells whose edges are tubes.

    points : (N, 3) cell seed sites ON the surface
             (:func:`surface_points` makes good ones; N = cell count).
    sheet  : SDF whose zero level set is the surface to decorate. The
             absolute value is used, so both signed solids
             (``sk.revolve_profile``) and unsigned sheets
             (:func:`revolved_sheet`) work. NOTE: a signed solid grows
             webs across its flat caps too - use :func:`revolved_sheet`
             when the mouth must stay open.
    strut_r: strut radius in mm (struts come out round; junctions where
             three cells meet are naturally a little thicker).

    How it works: ``web = (d2 - d1) / 2`` (distances to the two nearest
    seeds) is zero exactly on the boundary walls between Voronoi cells;
    combining it with the sheet distance as
    ``sqrt(web^2 + sheet^2) - strut_r`` leaves round tubes along the
    curves where those walls cross the surface.
    """
    from scipy.spatial import cKDTree

    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3 or len(pts) < 4:
        raise ValueError("points must be an (N >= 4, 3) array")
    tree = cKDTree(pts)
    r = float(strut_r)
    margin = r + 4.0  # past this the sheet term can't flip the sign

    def f(p):
        d, _ = tree.query(np.asarray(p, dtype=np.float64), k=2, workers=workers)
        web = (d[:, 1] - d[:, 0]) * 0.5
        out = web - r  # valid (sign-true) lower bound away from the walls
        near = web < margin
        if near.any():
            s = np.abs(np.asarray(sheet(p[near]), dtype=np.float64))
            out[near] = np.sqrt(web[near] ** 2 + s * s) - r
        return out.astype(_F)

    return f
