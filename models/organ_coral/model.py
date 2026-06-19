"""
Organ-pipe coral growth — exact envelope, organic interior.
See spec.md for the design intent; every tunable lives in params.json.

Run directly or via the standard runner:
    .venv\\Scripts\\python -m scripts.build_model models\\organ_coral
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
BASE_R = P["base_diameter_mm"] / 2
TOP_R = P["top_diameter_mm"] / 2
VOXEL = P["voxel_mm"]

# --- Exact silhouette: revolved concave profile ---------------------------
profile_pts, r_of_z = og.taper_profile(
    base_r=BASE_R, top_r=TOP_R, height=H, curve=P["profile_curve"]
)
envelope = sk.revolve_profile(profile_pts)

# --- Organic interior: wandering pipes following the taper ----------------
# Pipes are placed inside the envelope with clearance; the cluster's XY
# positions shrink with height along the normalized profile, so growth
# tracks the silhouette and the envelope only shaves the strays.
placement_r = BASE_R - P["tube_radius_max_mm"] - 2.0
tubes = og.organ_pipe_tubes(
    count=P["tube_count"],
    base_disk_r=placement_r,
    # Overshoot so the tallest pipes pierce the envelope top and get
    # trimmed perfectly flat at exactly H (even with height jitter).
    height=H * 1.08,
    min_height_frac=P["min_height_frac"],
    tube_r=(P["tube_radius_min_mm"], P["tube_radius_max_mm"]),
    taper=P["tube_taper"],
    radial_scale=lambda z: float(r_of_z(min(z, H))) / BASE_R,
    wander=P["tube_wander_mm"],
    steps=P["tube_steps"],
    center_tall=True,
    seed=P["seed"],
)
pipes = og.skeleton_sdf(tubes, blend=P["blend_mm"])

# --- Solid base disk (oversized; envelope trims it to exactly Ø base) -----
base = sk.cylinder(r=BASE_R + 3.0, h=2 * P["base_height_mm"], center=(0, 0, 0))

solid = sk.smooth_union(P["blend_mm"] * 1.6, base, pipes)

# --- Grown-surface noise (before the envelope, so dimensions stay exact) --
solid = sk.displace(
    solid,
    sk.fbm_noise(
        amplitude=P["noise_amplitude_mm"],
        frequency=P["noise_frequency"],
        octaves=3,
        seed=P["seed"] + 100,
    ),
)

# --- Open pipe mouths at every tip -----------------------------------------
mouth_cutters = []
for tip, tip_r in tubes.tips:
    bore_r = tip_r - P["mouth_wall_mm"]
    if bore_r < 0.8:
        continue
    mouth_cutters.append(
        sk.cylinder(
            r=bore_r,
            h=2 * P["mouth_depth_mm"],
            center=(tip[0], tip[1], min(tip[2], H)),
        )
    )
if mouth_cutters:
    solid = sk.smooth_subtract(0.8, solid, sk.union(*mouth_cutters))

# --- Exact dimensions: hard intersect with the envelope -------------------
# Pruned: the expensive pipe field is only evaluated inside the envelope.
solid = sk.intersect_pruned(envelope, solid, margin=4 * VOXEL)

# --- Mesh, verify the spec numbers, export --------------------------------
pad = 3 * VOXEL
m = sk.mesh(
    solid,
    bounds=((-BASE_R - pad, -BASE_R - pad, -pad), (BASE_R + pad, BASE_R + pad, H + pad)),
    voxel=VOXEL,
    decimate_to=P.get("decimate_to", 280000),
)

size = m.extents
spec = np.array([2 * BASE_R, 2 * BASE_R, H])
err = np.abs(size - spec)
print(f"target {spec[0]:.1f} x {spec[1]:.1f} x {spec[2]:.1f} mm")
print(f"actual {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm (err {err.max():.2f} mm)")
TOL = 0.8
if err.max() > TOL:
    print(f"ERROR: dimensions off by more than {TOL} mm", file=sys.stderr)
    sys.exit(1)

sk.save_stl(m, MODEL_DIR / "output" / "organ_coral.stl")
