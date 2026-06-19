"""
voronoi_funnel — twisted vase whose surface is an open Voronoi lattice.

See spec.md and refs/print_photo.png. Pipeline:
seeds on the revolved profile sheet -> voronoi_lattice (round struts on
cell edges) -> warp (wavy edges) -> clip -> + rim torus + base disk ->
twist everything (disk/rim are rotation-invariant; only the cells shear).

Run:  .venv\\Scripts\\python -m scripts.build_model models\\voronoi_funnel
"""

import json
import sys
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODEL_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402

from scripts import sdf_kit as sk  # noqa: E402
from scripts import organic as og  # noqa: E402

P = json.loads((MODEL_DIR / "params.json").read_text())
H = P["height_mm"]
STRUT_R = P["strut_radius_mm"]
RIM_R = P["rim_radius_mm"]
WARP_A = P["warp_amplitude_mm"]
VOXEL = P["voxel_mm"]
SEED = P["seed"]

# --- Profile: smooth the control points, then extend past both ends so the
# rim and base cells aren't starved of seeds (the overhang gets clipped).
ctrl = np.asarray(P["profile_r_z"], dtype=np.float64)
dense = sk._catmull_rom(ctrl, P["profile_smooth_samples"])
dense[:, 0] = np.maximum(dense[:, 0], 0.5)
ext_len = P["profile_extend_mm"]
t0 = dense[0] - dense[1]
t1 = dense[-1] - dense[-2]
t0 /= max(np.linalg.norm(t0), 1e-9)
t1 /= max(np.linalg.norm(t1), 1e-9)
ext = np.vstack([dense[0] + t0 * ext_len, dense, dense[-1] + t1 * ext_len])
ext[:, 0] = np.maximum(ext[:, 0], 0.5)

# --- Lattice on the sheet ---------------------------------------------------
sheet = og.revolved_sheet(ext)
boost = P.get("cell_density_bottom_boost", 1.0)
seeds = og.surface_points(
    ext,
    count=P["cell_count"],
    relax_iters=P["cell_relax_iters"],
    # Like the reference print: small/dense cells low, opening up going up
    density=lambda r, z: 1.0 + (boost - 1.0) * max(0.0, 1.0 - z / H),
    seed=SEED,
)
lattice = og.voronoi_lattice(seeds, sheet, strut_r=STRUT_R)
if WARP_A > 0:
    lattice = sk.warp(lattice, WARP_A, P["warp_frequency"], seed=SEED + 9)

# Clip to the body: z=0 up to the rim centerline (rim tube tops out at H).
z_rim = H - RIM_R
lattice = sk.intersect(
    lattice,
    sk.half_space((0, 0, 1), z_rim),
    sk.half_space((0, 0, -1), 0.0),
)

# --- Precise, unwarped parts: mouth rim + base disk --------------------------
r_rim = float(np.interp(z_rim, dense[:, 1], dense[:, 0]))
rim = sk.torus(r_rim, RIM_R, center=(0, 0, z_rim))
disk = sk.cylinder(
    P["base_disk_radius_mm"],
    P["base_disk_height_mm"],
    center=(0, 0, P["base_disk_height_mm"] / 2),
)

solid = sk.smooth_union(P["blend_mm"], lattice, rim, disk)
if P["twist_deg"]:
    solid = sk.twist(solid, P["twist_deg"] / H)

# --- Mesh, self-check, export -------------------------------------------------
r_body = float(dense[dense[:, 1] <= z_rim, 0].max())
r_out = max(r_body + STRUT_R + WARP_A, r_rim + RIM_R, P["base_disk_radius_mm"])
pad = 3 * VOXEL
m = sk.mesh(
    solid,
    bounds=((-r_out - pad, -r_out - pad, -pad), (r_out + pad, r_out + pad, H + pad)),
    voxel=VOXEL,
    decimate_to=P.get("decimate_to"),
)

size = m.extents
exp_xy = 2 * max(r_body + STRUT_R, r_rim + RIM_R, P["base_disk_radius_mm"])
print(f"target ~{exp_xy:.1f} x ~{exp_xy:.1f} x {H:.1f} mm")
print(f"actual {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm")
err_z = abs(size[2] - H)
err_xy = max(abs(size[0] - exp_xy), abs(size[1] - exp_xy))
if err_z > max(0.6, 2 * VOXEL) or err_xy > 1.0 + WARP_A:
    print(f"ERROR: dimensions out of tolerance (xy err {err_xy:.2f}, z err {err_z:.2f})", file=sys.stderr)
    sys.exit(1)

sk.save_stl(m, MODEL_DIR / "output" / "voronoi_funnel.stl")
