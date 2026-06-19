"""
Template model — copy this whole folder to models/<your_name>/ and edit.

Contract (see AGENTS.md):
- read every tunable from params.json
- build in mm, Z up, sitting on z=0
- enforce hard dimensions geometrically (primitive sizes or an envelope)
- self-check dimensions, exit non-zero on failure
- write STL(s) into ./output/

Run:  .venv\\Scripts\\python -m scripts.build_model models\\<your_name>
"""

import json
import sys
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODEL_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402

from scripts import sdf_kit as sk  # noqa: E402
from scripts import organic as og  # noqa: E402,F401  (skeletons, envelopes)

P = json.loads((MODEL_DIR / "params.json").read_text())
W, D, H = P["width_mm"], P["depth_mm"], P["height_mm"]
VOXEL = P["voxel_mm"]

# --- Build the shape (replace this block) ----------------------------------
solid = sk.rounded_box((W, D, H), radius=P["corner_radius_mm"], center=(0, 0, H / 2))

if P["noise_amplitude_mm"] > 0:
    solid = sk.displace(
        solid,
        sk.fbm_noise(
            amplitude=P["noise_amplitude_mm"],
            frequency=P["noise_frequency"],
            seed=P["seed"],
        ),
    )

# --- Mesh, self-check, export (keep this tail) ------------------------------
pad = 3 * VOXEL
m = sk.mesh(
    solid,
    bounds=((-W / 2 - pad, -D / 2 - pad, -pad), (W / 2 + pad, D / 2 + pad, H + pad)),
    voxel=VOXEL,
    decimate_to=P.get("decimate_to"),
)

size = m.extents
spec = np.array([W, D, H])
err = float(np.abs(size - spec).max())
print(f"target {W} x {D} x {H} mm | actual {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} (err {err:.2f})")
if err > 0.5 + P["noise_amplitude_mm"]:
    print("ERROR: dimensions out of tolerance", file=sys.stderr)
    sys.exit(1)

sk.save_stl(m, MODEL_DIR / "output" / f"{MODEL_DIR.name}.stl")
