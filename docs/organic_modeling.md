# Organic Modeling Cookbook (SDF toolkit)

Recipes for the shapes CSG can't do: coral, antlers, bones, blobby
smooth-blended forms, noise-displaced surfaces, and open-cell Voronoi
lattices. Everything here is built on `scripts/sdf_kit.py` (primitives,
booleans, modifiers, meshing) and `scripts/organic.py` (skeletons,
branches, tube clusters, lattice helpers).

If you only read one thing, read **AGENTS.md** first — this file is the
expanded "how" behind its *SDF toolkit in 60 seconds* section. Two worked,
runnable models live in the repo and are the best reference of all:

- `models/organ_coral/` — organ-pipe coral with an **exact** base/top/height envelope.
- `models/voronoi_funnel/` — revolved Voronoi-lattice shell with a rim.

Units are **mm, Z up, model sits on z=0**. Everything is deterministic:
all randomness flows from `seed`.

---

## The mental model

Every shape is a **signed distance function** (SDF): a callable
`f(points) -> distances` where `points` is an `(N, 3)` array and the result
is `(N,)` — **negative inside** the solid, **positive outside**, zero on the
surface. You compose these callables, then polygonize with marching cubes:

```python
from scripts import sdf_kit as sk

f = sk.smooth_union(2.5, sk.sphere(12), sk.sphere(9, center=(0, 0, 14)))
m = sk.mesh(f, bounds=((-15, -15, -14), (15, 15, 26)), voxel=0.4)
sk.save_stl(m, "blob.stl")   # welded -> watertight, survives the STL round-trip
```

`sk.mesh` returns a `trimesh.Trimesh`. It welds the result through the
Manifold kernel, so watertightness survives the float32 STL round-trip —
**always go through `sk.mesh` / `sk.save_stl`**, never hand-roll marching
cubes output (raw output won't survive export; see AGENTS troubleshooting).

---

## API at a glance (verified against the source)

**Primitives** (`sk.`): `sphere(r, center)`, `box(size, center)`,
`rounded_box(size, radius, center)`, `cylinder(r, h, center)`,
`capsule(p0, p1, r)`, `capped_cone(p0, p1, r0, r1)`,
`cone_capsule(p0, p1, r0, r1)`, `torus(R, r, center)`,
`ellipsoid(radii, center)`, `half_space(normal, offset_d)`,
`revolve_profile(profile_pts, smooth_samples)`.

**Booleans** (`sk.`): `union`, `intersect`, `subtract(base, cutter)`;
smooth variants `smooth_union(k, *fs)`, `smooth_intersect(k, *fs)`,
`smooth_subtract(k, base, cutter)` where `k` is the blend radius in mm;
and `intersect_pruned(outer, inner, margin)` — a cheap envelope that gates
an expensive interior.

**Modifiers** (`sk.`): `translate`, `rotate(f, axis, deg)`, `scale`
(uniform only), `offset(f, d)`, `shell(f, thickness)`,
`displace(f, g)`, `twist(f, deg_per_mm)`,
`warp(f, amplitude, frequency, octaves, seed)`, `repeat_polar(f, count)`,
`mirror_x(f)`.

**Noise** (`sk.`): `fbm_noise(amplitude, frequency, octaves, lacunarity,
gain, seed)` -> a scalar field for `displace`. `frequency` is cycles/mm
(0.05–0.2 = broad lumps, 0.5+ = fine grain).

**Meshing** (`sk.`): `mesh(f, bounds, voxel=0.5, block=48, keep="largest",
min_component_volume=1.0, decimate_to=None)` and `save_stl(m, path)`.

**Organic** (`og.`): `Skeleton` (`.add`, `.add_path`, `.bounds`),
`skeleton_sdf(skel, blend)`, `grow_branches(...)`, `organ_pipe_tubes(...)`,
`taper_profile(base_r, top_r, height, curve) -> (profile_pts, radius_of_z)`,
`phyllotaxis_disk(count, radius)`, `revolved_sheet(profile_pts,
smooth_samples)`, `surface_points(profile_pts, count, ...)`,
`voronoi_lattice(points, sheet, strut_r)`.

---

## Recipe 1 — blobby smooth-blended form

`smooth_union`'s first argument is the blend distance `k` in mm: larger `k`
melts neighbors together more (2–4 mm reads as fleshy/coral; 0.5–1 keeps
parts crisp). Layer noise on with `displace` for surface texture.

```python
from scripts import sdf_kit as sk

body = sk.smooth_union(
    3.0,
    sk.sphere(14),
    sk.sphere(10, center=(0, 0, 18)),
    sk.capsule((0, 0, 0), (12, 0, 22), 4),
)
body = sk.displace(body, sk.fbm_noise(amplitude=0.6, frequency=0.18, seed=7))
m = sk.mesh(body, bounds=((-20, -20, -16), (24, 20, 30)), voxel=0.4)
sk.save_stl(m, "models/blob/output/blob.stl")
```

Rule of thumb: keep noise amplitude smaller than your real features, and
the **voxel finer than the noise amplitude** (else the texture aliases into
gravel — see AGENTS troubleshooting).

---

## Recipe 2 — antler / branching coral

`grow_branches` returns a `Skeleton` (a bag of tapered segments). Turn it
into a solid with `skeleton_sdf(skel, blend)`. Size the mesh `bounds` from
the skeleton itself via `skel.bounds(margin)`.

```python
from scripts import sdf_kit as sk
from scripts import organic as og

skel = og.grow_branches(
    length=90, radius=7, levels=4, splits=(2, 3),
    split_angle=38, up_bias=0.25, wander=10, min_radius=0.8, seed=11,
)
f = og.skeleton_sdf(skel, blend=2.5)

lo, hi = skel.bounds(margin=4.0)       # auto-fit the evaluation box
m = sk.mesh(f, bounds=(lo, hi), voxel=0.5, decimate_to=250_000)
sk.save_stl(m, "models/antler/output/antler.stl")
```

Key dials: `wander` (per-step bend, gnarliness), `up_bias` (0..1 pull toward
+Z; negative droops), `radius_decay` (how fast children thin), `min_radius`
(stop-splitting floor — keep ≥ ~0.8 mm so tips are printable).

---

## Recipe 3 — exact dimensions via an envelope (the important one)

When the spec gives **hard numbers** ("base Ø90, top Ø36, height 140"), do
not hope the organic growth lands on them. Build the interior however you
like, then **intersect it with an exact envelope** — the envelope is
authoritative, the growth is decoration (AGENTS golden rule 5). This is the
`models/organ_coral/` pattern:

```python
from scripts import sdf_kit as sk
from scripts import organic as og

# Exact silhouette: base radius 45, top radius 18, height 140, slight concave.
prof, r_of_z = og.taper_profile(base_r=45, top_r=18, height=140, curve=1.2)
envelope = sk.revolve_profile(prof, smooth_samples=64)   # closed solid

# Organic interior: a cluster of tubes that pulls inward as the envelope narrows.
skel = og.organ_pipe_tubes(
    count=40, base_disk_r=38, height=140,
    radial_scale=lambda z: r_of_z(z) / r_of_z(0), seed=3,
)
interior = og.skeleton_sdf(skel, blend=2.0)

# intersect_pruned: only evaluate the expensive interior near the envelope.
f = sk.intersect_pruned(envelope, interior, margin=2.0)

m = sk.mesh(f, bounds=((-48, -48, -2), (48, 48, 143)), voxel=0.45)
sk.save_stl(m, "models/organ_coral/output/organ_coral.stl")
```

After building, the bounding box should match the spec to tolerance —
that's the point of the envelope. If the bbox comes out slightly *smaller*
than spec, the bounds clipped the model: grow `bounds` by ~3×voxel on each
side (border faces get capped flat to keep the mesh closed).

---

## Recipe 4 — open-cell Voronoi lattice shell

The "printed voronoi vase/lamp" look: round struts running along the edges
of Voronoi cells laid on a surface of revolution. Three steps — define the
surface as a `(radius, z)` profile, scatter blue-noise cell seeds on it,
then build the strut web. This is the `models/voronoi_funnel/` pattern:

```python
from scripts import sdf_kit as sk
from scripts import organic as og

profile = [(34, 0), (46, 20), (40, 60), (54, 140), (74, 160)]  # (radius, z)

sheet = og.revolved_sheet(profile, smooth_samples=96)          # UNSIGNED sheet, no caps
seeds = og.surface_points(profile, count=180, smooth_samples=96, seed=5)
web   = og.voronoi_lattice(seeds, sheet, strut_r=1.6)

m = sk.mesh(web, bounds=((-78, -78, -2), (78, 78, 163)), voxel=0.4,
            decimate_to=300_000)
sk.save_stl(m, "models/voronoi_funnel/output/voronoi_funnel.stl")
```

Notes that bite if you skip them:
- Use **`revolved_sheet`** (unsigned, no caps), *not* `sk.revolve_profile`,
  when the mouth must stay open — a signed solid grows webs across its flat
  top and bottom caps too.
- `surface_points(count=...)` sets the **cell count**. `strut_r` is the tube
  radius; junctions where three cells meet come out naturally thicker.
- More relaxation (`relax_iters`) = more even cells; `density=lambda r, z:
  ...` gives a cell-size gradient (small cells low, big cells high).
- Want a solid rim/base? Build it separately (e.g. `sk.revolve_profile` of a
  short ring) and `sk.union` it on **after** the lattice — see the worked
  model.

---

## Performance & quality

| Situation | What to do |
|---|---|
| First look / iterating shape | `voxel` 0.8–1.0 (seconds) |
| Final export, organic surface | `voxel` 0.4–0.5 (a minute or two) |
| Surface noise must show | keep `voxel` ≤ noise amplitude |
| Big STL (>20 MB) | pass `decimate_to=250_000` to `sk.mesh` |
| Hundreds of skeleton segments | `intersect_pruned` with a cheap envelope; keep `block=48` |
| Grid too big (MemoryError) | raise `voxel` or shrink `bounds` (`sk.mesh` refuses >~1.5 GB grids) |

`sk.mesh` prints the grid size, eval/marching-cubes time, final triangle
count, bbox, and watertightness. Read that line every run.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `SDF is positive everywhere in bounds` | Bounds don't contain the model — check units/placement |
| bbox slightly smaller than spec | Bounds clipped it (border capping) — grow `bounds` by ~3×voxel |
| Not watertight after my own mesh code | Go through `sk.mesh` / `mesh_tools.weld`; raw marching cubes won't survive float32 STL |
| Surface looks like gravel | Noise `frequency` too high, or `voxel` too coarse for the amplitude |
| Tubes look like stacked beads | Too few path steps / too much wander — raise `steps`, lower `wander` |
| Lattice mouth closed over | Used a signed solid as the sheet — use `og.revolved_sheet` instead |

---

## The loop (don't skip the LOOK step)

1. Write `spec.md` (plain description + a hard-dimensions table).
2. Put every tunable number in `params.json`.
3. Write `model.py` (copy `models/_template/`), enforce hard dims via an
   envelope, self-check dims before export.
4. `.venv\Scripts\python -m scripts.build_model models\<name>` — generates,
   validates, renders preview PNGs, writes `output/report.json`.
5. **Open `output/<name>_preview.png` and compare it to `spec.md`.** This is
   the core of the loop — an STL that validates can still be the wrong shape.
6. Adjust params, repeat. Coarse voxel while iterating; fine voxel for the
   last pass.
