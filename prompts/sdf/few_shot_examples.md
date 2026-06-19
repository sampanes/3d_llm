# SDF Pipeline — Few-Shot Examples

Worked, verified examples for the `sdf` pipeline. Each pairs a natural-language
request with a complete script that follows the system prompt contract: exact
envelope, organic interior, `intersect_pruned`, dimension self-check, and a
final `sk.save_stl(m, "model.stl")`.

---

## Example 1

**Request:** "An organ-pipe coral colony: round base exactly 90 mm across,
120 mm tall, narrowing to about 45 mm at the top. Lots of wandering vertical
tubes, looks grown, prints without supports."

```python
# Organ-pipe coral colony: base exactly D90, height exactly 120, silhouette
# narrowing to D45 at the top. Units mm, Z up, sits on z=0.

import sys

import numpy as np

from scripts import sdf_kit as sk
from scripts import organic as og

BASE_D, TOP_D, H = 90.0, 45.0, 120.0
VOXEL = 0.8            # iterate at 0.8-1.5; drop to 0.5 for the final export
SEED = 7

# Exact silhouette: revolved concave taper. The envelope owns the dimensions.
profile_pts, r_of_z = og.taper_profile(BASE_D / 2, TOP_D / 2, H, curve=0.8)
envelope = sk.revolve_profile(profile_pts)

# Organic interior: wandering tubes placed inside the envelope with clearance,
# pulled inward with height so growth tracks the silhouette. Overshoot the
# height so the tallest tubes pierce the top and get trimmed dead flat.
placement_r = BASE_D / 2 - 5.5 - 2.0
tubes = og.organ_pipe_tubes(
    count=26,
    base_disk_r=placement_r,
    height=H * 1.06,
    min_height_frac=0.55,
    tube_r=(3.0, 5.5),
    taper=0.85,
    radial_scale=lambda z: float(r_of_z(min(z, H))) / (BASE_D / 2),
    wander=2.5,
    steps=12,
    center_tall=True,
    seed=SEED,
)
pipes = og.skeleton_sdf(tubes, blend=2.2)

# Solid base disk for bed adhesion (oversized; the envelope trims it exact).
base = sk.cylinder(r=BASE_D / 2 + 3, h=12.0, center=(0, 0, 0))
solid = sk.smooth_union(3.5, base, pipes)

# Grown-surface noise BEFORE the envelope, so hard dimensions stay exact.
solid = sk.displace(
    solid, sk.fbm_noise(amplitude=0.5, frequency=0.12, octaves=3, seed=SEED + 1)
)
solid = sk.intersect_pruned(envelope, solid, margin=4 * VOXEL)

pad = 3 * VOXEL
m = sk.mesh(
    solid,
    bounds=((-BASE_D / 2 - pad, -BASE_D / 2 - pad, -pad),
            (BASE_D / 2 + pad, BASE_D / 2 + pad, H + pad)),
    voxel=VOXEL,
    decimate_to=250_000,
)
size = m.extents
err = np.abs(size - np.array([BASE_D, BASE_D, H]))
print(f"actual {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm (err {err.max():.2f})")
if err.max() > max(0.8, VOXEL):
    print("dimensions out of tolerance", file=sys.stderr)
    sys.exit(1)

sk.save_stl(m, "model.stl")
```

---

## Example 2

**Request:** "Make an organic shape similar to a triangular prism with
coral/skeleton frameworks, from a 14 inch x 5 inch base up to a 14 inch top
edge that is perfectly horizontal and rounded slightly, struts about the
thickness of a pencil."

```python
# Organic coral-framework triangular prism.
# Base 355.6 x 127 mm (14 x 5 in), ridge top exactly 177.8 mm (7 in, assumed
# since the request gave no height), top edge horizontal and rounded to pencil
# radius, struts about pencil thickness. Units mm, Z up, sits on z=0.

import sys

import numpy as np

from scripts import sdf_kit as sk
from scripts import organic as og

L = 14 * 25.4          # 355.6 prism length along X
W = 5 * 25.4           # 127.0 base depth along Y
H = 7 * 25.4           # 177.8 ridge height (assumption, stated above)
R = 3.8                # pencil radius: rounds the ridge, sizes the top bar
STRUT_R = 4.0          # pencil-thick coral struts
VOXEL = 0.8            # iterate at 1.5-2.0; final export at 0.5-0.8
SEED = 11

# --- Envelope: exact triangular prism with a rounded horizontal ridge -----
# Ridge = cylinder along X, radius R, top exactly at z=H.
zc = H - R
# Slanted faces are tangent lines from the base corners (y=+/-W/2, z=0) to
# the ridge circle (center (0, zc), radius R), so faces meet the rounding
# seamlessly at the tangent height and the base stays exactly W wide.
P = np.array([W / 2, 0.0])            # right base corner in (y, z)
C = np.array([0.0, zc])               # ridge circle center in (y, z)
d = C - P
dist = float(np.hypot(*d))
a = float(np.arcsin(R / dist))        # rotate P->C by the tangent angle
ca, sa = np.cos(a), np.sin(a)
t = np.array([d[0] * ca + d[1] * sa, -d[0] * sa + d[1] * ca]) / dist
n2 = np.array([t[1], -t[0]])          # outward unit normal of the right face
if n2[0] < 0:
    n2 = -n2
assert abs(abs(float(n2 @ d)) - R) < 1e-6  # really tangent to the ridge
z_t = zc + R * abs(n2[1])             # tangent height: wall meets rounding

slant_r = sk.half_space((0.0, n2[0], n2[1]), float(n2 @ P))
slant_l = sk.half_space((0.0, -n2[0], n2[1]), float(n2 @ P))
bottom = sk.half_space((0, 0, -1), 0.0)            # solid above z=0
end_a = sk.half_space((1, 0, 0), L / 2)            # |x| <= L/2
end_b = sk.half_space((-1, 0, 0), L / 2)
# Ridge rod along X: a long capsule (round ends land outside the end planes
# and get trimmed off, leaving a clean cylinder).
ridge = sk.capsule((-L, 0, zc), (L, 0, zc), R)
wedge = sk.intersect(slant_r, slant_l, bottom, end_a, end_b)
cap = sk.union(sk.half_space((0, 0, 1), z_t), ridge)
envelope = sk.intersect(wedge, cap)

# --- Interior: base slab + coral trees + solid bar under the ridge --------
slab = sk.box((L + 20, W + 20, 8), center=(0, 0, 0))   # trimmed to footprint
beam = sk.capsule((-L / 2 - 5, 0, zc), (L / 2 + 5, 0, zc), R + 2.0)

trees = []
xs = np.linspace(-L / 2 * 0.86, L / 2 * 0.86, 9)
rng = np.random.default_rng(SEED)
for i, x in enumerate(xs):
    skel = og.grow_branches(
        origin=(float(x), float(rng.uniform(-W / 5, W / 5)), 0.0),
        direction=(float(rng.uniform(-0.3, 0.3)), float(rng.uniform(-0.35, 0.35)), 1.0),
        length=H * 0.5,
        radius=STRUT_R,
        levels=5,
        splits=(2, 3),
        split_angle=36.0,
        wander=11.0,
        up_bias=0.3,
        radius_decay=0.8,
        min_radius=1.2,
        steps_per_branch=5,
        seed=SEED + i * 7,
    )
    trees.append(og.skeleton_sdf(skel, blend=2.5))

interior = sk.smooth_union(3.0, slab, beam, *trees)
interior = sk.displace(
    interior, sk.fbm_noise(amplitude=0.5, frequency=0.1, octaves=3, seed=SEED)
)

solid = sk.intersect_pruned(envelope, interior, margin=4 * VOXEL)

# --- Mesh, self-check the spec dimensions, export -------------------------
pad = 3 * VOXEL
m = sk.mesh(
    solid,
    bounds=((-L / 2 - pad, -W / 2 - pad, -pad), (L / 2 + pad, W / 2 + pad, H + pad)),
    voxel=VOXEL,
    decimate_to=250_000,
)
size = m.extents
spec = np.array([L, W, H])
err = np.abs(size - spec)
print(f"target {spec[0]:.1f} x {spec[1]:.1f} x {spec[2]:.1f} mm")
print(f"actual {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm (err {err.max():.2f})")
if err.max() > max(0.8, VOXEL):
    print("ERROR: dimensions out of tolerance", file=sys.stderr)
    sys.exit(1)

sk.save_stl(m, "model.stl")
```

---

## Example 3

**Request:** "A voronoi lattice vase like the 3D-printed ones: the whole
surface is open polygonal cells with round struts, no solid skin. Curvy
silhouette with a bulge and a waist, mouth exactly 100 mm across, 140 mm
tall, cells spiraling upward, denser near the bottom. Smooth rim, thin
base disk."

```python
# Voronoi lattice vase: open polygonal cells with round struts on a curvy
# vase silhouette. Mouth outer diameter exactly 100, height exactly 140.
# Units mm, Z up, sits on z=0.

import sys

import numpy as np

from scripts import sdf_kit as sk
from scripts import organic as og

MOUTH_OD = 100.0       # rim torus owns this dimension exactly
H = 140.0              # rim tube tops out exactly here
STRUT_R = 1.4          # cell-edge strut radius (struts come out ~2.8 mm)
RIM_R = 2.0            # smooth continuous mouth band
WARP_A = 1.2           # wavy organic cell edges (keep < RIM_R)
CELLS = 150
VOXEL = 0.6
SEED = 3

# --- Vase profile (radius, z): bulge, waist, flare. Keep every body radius
# + STRUT_R + WARP_A inside MOUTH_OD/2 so the rim torus governs the bbox.
ctrl = np.array([[30.0, 0.0], [42.0, 25.0], [33.0, 60.0], [40.0, 100.0], [46.5, 140.0]])
dense = sk._catmull_rom(ctrl, 96)
# Extend past both ends so rim/base cells aren't starved (overhang is clipped)
t0 = dense[0] - dense[1]
t1 = dense[-1] - dense[-2]
ext = np.vstack([dense[0] + t0 / np.linalg.norm(t0) * 10,
                 dense,
                 dense[-1] + t1 / np.linalg.norm(t1) * 10])
ext[:, 0] = np.maximum(ext[:, 0], 0.5)

# --- Voronoi lattice on the sheet: seeds -> round struts on cell edges
sheet = og.revolved_sheet(ext)
seeds = og.surface_points(
    ext, count=CELLS, relax_iters=6,
    density=lambda r, z: 1.0 + 0.8 * max(0.0, 1.0 - z / H),  # denser low
    seed=SEED,
)
lattice = og.voronoi_lattice(seeds, sheet, strut_r=STRUT_R)
lattice = sk.warp(lattice, WARP_A, frequency=0.035, seed=SEED + 9)

# Clip to the body; the rim torus then tops out at exactly z = H.
z_rim = H - RIM_R
lattice = sk.intersect(
    lattice, sk.half_space((0, 0, 1), z_rim), sk.half_space((0, 0, -1), 0.0)
)

# --- Precise, UNwarped parts: mouth rim (exact OD) + flat base disk
rim = sk.torus(MOUTH_OD / 2 - RIM_R, RIM_R, center=(0, 0, z_rim))
disk = sk.cylinder(35.0, 2.4, center=(0, 0, 1.2))
solid = sk.smooth_union(1.5, lattice, rim, disk)
solid = sk.twist(solid, 100.0 / H)  # spiral cell flow; rim/disk are invariant

# --- Mesh, self-check, export
pad = 3 * VOXEL
r_out = MOUTH_OD / 2 + pad
m = sk.mesh(
    solid,
    bounds=((-r_out, -r_out, -pad), (r_out, r_out, H + pad)),
    voxel=VOXEL,
    decimate_to=250_000,
)
size = m.extents
spec = np.array([MOUTH_OD, MOUTH_OD, H])
err = np.abs(size - spec)
print(f"target {spec[0]:.1f} x {spec[1]:.1f} x {spec[2]:.1f} mm")
print(f"actual {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm (err {err.max():.2f})")
if err.max() > max(1.5, 2 * VOXEL):
    print("ERROR: dimensions out of tolerance", file=sys.stderr)
    sys.exit(1)

sk.save_stl(m, "model.stl")
```

---

## Why these are shaped this way

- **The envelope owns every hard dimension.** Interiors are grown oversized
  and shaved by `intersect_pruned`, so user numbers survive any amount of
  organic wandering.
- **Noise displaces the interior, never the envelope.**
- **Self-checks make failures loud:** a wrong-sized model exits nonzero and
  the pipeline reports it instead of delivering a bad STL.
- **Capsules between points replace rotated cylinders** — `sk.rotate` spins
  the field about the origin, which is easy to get wrong.
- **Several small trees beat one big tree** for filling wide footprints.
- **"Skeleton/lattice surface" requests are voronoi shells, not coral:**
  cells on a sheet (`voronoi_lattice`), warped for organic edges, finished
  with UNwarped precise parts (rim torus, flat disk) that own the hard
  dimensions, then twisted — twist leaves anything rotationally symmetric
  untouched, so only the cell pattern spirals.
