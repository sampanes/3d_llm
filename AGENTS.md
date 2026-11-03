# AGENTS.md — How to create 3D models in this repo

This file is the **canonical workflow contract** for any coding agent (Claude
Code, Antigravity, Cursor, Codex, …) asked to create or edit a 3D model here.
Humans: README.md is the gentler overview; everything below also works typed
by hand.

Everything in this file was actually run and verified on 2026-06-10 on this
machine (Windows 10, Python 3.11 venv at `.venv`, portable OpenSCAD in
`tools/openscad/`). No API keys are required for any of it.

---

## Golden rules

1. **Units are mm. Z is up. Models sit on Z=0** (bottom of part touches the
   build plate at z=0, centered on the XY origin).
2. **One model = one folder**: `models/<name>/` containing `spec.md`
   (what was asked, with a dimensions table), `params.json` (every tunable
   number), and `model.py` (the generator). Outputs land in
   `models/<name>/output/` (gitignored — params + code are the source of truth).
3. **Determinism**: all randomness comes from `seed` values in `params.json`.
   Same params → same STL, forever.
4. **Never deliver an STL you haven't validated AND looked at.** The build
   runner validates and renders previews automatically; open the preview PNG
   with your image-reading ability and compare it against `spec.md`.
5. **Exact dimensions come from geometry, not hope.** When the user gives
   hard numbers ("base Ø90, height 140"), enforce them with an envelope —
   build the organic interior however you like, then
   `sk.intersect_pruned(envelope, interior)`. The envelope is authoritative;
   the growth is decoration. See `models/organ_coral/` for the worked example.
6. **Iterate coarse, finish fine.** First passes at `voxel_mm` 0.8–1.0
   (seconds–tens of seconds), final export at 0.4–0.5 (a minute or two).
7. Run everything through the venv interpreter: `.venv\Scripts\python`.
   Never install packages globally; never assume `python` on PATH is the venv.

---

## Characters and animals (Hello Kitty, a lion): read before building one

Added 2026-11-02, after Hello Kitty and a lion's legs both came out as elementary shapes warped
onto each other. Unlike the rest of this file, nothing in this section has been run yet.

Switching code backends does not fix that. An LLM places primitives by guessed numbers, and a hard
union of a cylinder into a sphere reads as a leg stuck on a body whichever backend draws it. There
are two routes, cheapest first:

1. **Inside this repo, for simple characters.** Use the SDF kit with `sk.smooth_union` (blend
   radius 2-4 mm) instead of hard unions. Make limbs from `og.Skeleton` + `og.skeleton_sdf` or
   `sk.cone_capsule` so they taper and blend into the body. Take proportions from a reference image
   in `models/<name>/refs/`. Hello Kitty (an ellipsoid head, a bow, a body) is winnable this way.
   A lion stays a stylized toy.
2. **An image-to-3D model, outside this repo, for likeness.** Run `nvidia-smi` first, because the
   GPU decides which one:

| Repo | Needs | How |
|---|---|---|
| [Tencent/Hunyuan3D-2](https://github.com/Tencent/Hunyuan3D-2) | NVIDIA GPU, 6 GB VRAM for shape only (a print needs no texture). Windows, macOS, Linux. | Clone it next to this repo, not inside it, with its own venv. Install PyTorch for the GPU, then `pip install -r requirements.txt` and `pip install -e .`. Skip the two texture extensions. `python gradio_app.py --disable_tex --low_vram_mode --host 127.0.0.1` serves a local page: image in, mesh out. Without `--host` it listens on every interface. |
| [microsoft/TRELLIS.2](https://github.com/microsoft/TRELLIS.2) | NVIDIA GPU, 24 GB VRAM. Tested on Linux only. | `setup.sh --new-env`, then `python app.py`. The Blender front end is [StableGen](https://github.com/sakalond/StableGen/wiki/TRELLIS.2-mesh-generation), which drives a local ComfyUI with the [ComfyUI-TRELLIS2](https://github.com/PozzettiAndrea/ComfyUI-TRELLIS2) node. |

Either way, the mesh then comes back here for the normal loop:
`edit_stl convert in.glb -o model.stl`, then `edit_stl repair`, `edit_stl scale --to-z <mm>`,
`validate_stl` and `mesh_preview`, and you LOOK at it. More background, plus which Blender "AI"
add-ons are worth anything, is in `docs/resources.md` under "Neural 3D Generation".

---

## Choosing the right backend

| Request smells like… | Use | Why |
|---|---|---|
| Boxes, brackets, mounts, enclosures, threads, gears | **OpenSCAD** (`templates/openscad/`, BOSL2 is bundled) | LLMs write it fluently; compiles in ms with the Manifold backend |
| Precise mechanical part needing fillets/chamfers/STEP export | **CadQuery** (`templates/cadquery/`) | Real B-rep kernel, exact dims, `.fillet()` |
| Coral, antlers, bones, plants, blobby/grown/melted anything | **SDF toolkit** (`scripts/sdf_kit.py` + `scripts/organic.py`) | Smooth blending, noise, branching — impossible in CSG |
| Voronoi lattice / open-cell shells (vases, lamps, "skeleton" surfaces) | **SDF toolkit**: `og.voronoi_lattice` (worked example: `models/voronoi_funnel/`) | Round struts along Voronoi cell edges on any revolved surface |
| "Edit this STL" (scale, hollow, cut, repair, merge) | **`scripts/edit_stl.py`** | Works on any mesh, no source needed |
| A recognizable character or animal (Hello Kitty, a lion), anything that must look like a reference | **SDF kit with smooth blends** for simple ones, else **image-to-3D** (Hunyuan3D-2, TRELLIS.2), then repair/scale here. See "Characters and animals" above | Parametric code can't do likeness |

Mixing is normal: grow an organic SDF part, then boolean a CadQuery-precise
mount onto it with `edit_stl boolean`.

---

## The loop (what "do it reliably" means)

```
1. CAPTURE   Write models/<name>/spec.md — plain-language description,
             a table of hard dimensions with tolerances, look references,
             print notes. If the user gave images, list them here.
2. PARAMS    Put every number you might tune into params.json.
3. GENERATE  Write model.py (start from models/_template/). Read params.json,
             build the shape, enforce hard dims via envelope/primitives,
             self-check dims before export, write STL to output/.
4. BUILD     .venv\Scripts\python -m scripts.build_model models\<name>
             → runs model.py, validates every STL, renders preview PNGs,
             writes output/report.json. Non-zero exit = not done.
5. LOOK      Open output/<name>_preview.png (agents: use your image input).
             Compare silhouette, proportions, detail against spec.md.
6. ITERATE   Adjust params.json (or model.py), go to 4. Coarse voxel while
             iterating; final voxel for the last pass.
7. DONE when build_model prints ALL CHECKS PASSED, dims are within spec
             tolerance, and the preview matches the spec visually.
             Tell the user the STL path + final dims + tri count.
```

For **image-reference requests** ("make an antler like these photos"): put the
images in `models/<name>/refs/`, describe in spec.md what features matter
(beam curve, number of tines, proportions), then iterate the loop comparing
your preview renders against the refs side by side.

---

## Toolbox (all verified working)

| Command | What it does |
|---|---|
| `.venv\Scripts\python -m scripts.build_model models\<name>` | Run a model folder end-to-end: generate → validate → preview → report |
| `.venv\Scripts\python -m scripts.mesh_preview FILE.stl` | 4-view contact-sheet PNG of any mesh (`--views iso,front,right,top,back,left,bottom`, `--separate`) |
| `.venv\Scripts\python -m scripts.validate_stl FILE.stl` | Watertight/volume/bbox report (`--json`) |
| `.venv\Scripts\python -m scripts.edit_stl info FILE.stl` | Dimensions, volume, watertightness |
| `.venv\Scripts\python -m scripts.edit_stl scale FILE --to-z 120` | Scale uniformly to exact size (`--factor`, `--to-x/y/z`, `--stretch`) |
| `.venv\Scripts\python -m scripts.edit_stl repair FILE` | Fix winding/holes; voxel-remesh fallback (`--force-remesh`) |
| `.venv\Scripts\python -m scripts.edit_stl hollow FILE --wall 2.5` | Shell out the interior (sealed cavity — add drain holes!) |
| `.venv\Scripts\python -m scripts.edit_stl boolean difference A.stl B.stl` | union / difference / intersection (manifold engine) |
| `.venv\Scripts\python -m scripts.edit_stl cut FILE --z 40 --keep below` | Capped planar cut |
| `.venv\Scripts\python -m scripts.edit_stl decimate FILE --ratio 0.3` | Reduce triangle count |
| `.venv\Scripts\python -m scripts.edit_stl smooth FILE --iterations 10` | Taubin smoothing |
| `.venv\Scripts\python -m scripts.edit_stl convert FILE -o out.3mf` | STL/OBJ/PLY/GLB/3MF conversion |
| `.venv\Scripts\python -m scripts.openscad_runner render F.scad -o F.stl` | Compile OpenSCAD (portable binary, BOSL2 include path, Manifold backend — automatic) |
| `.venv\Scripts\python -m scripts.openscad_runner check F.scad` | Syntax-check a .scad without rendering |
| `.venv\Scripts\python -m scripts.generate -p "..." --llm anthropic` | Tier B: API-driven generation (needs key in `.env`); `--pipeline sdf` for organic shapes; `--image photo.jpg` sends reference image(s) the LLM sees |
| `.venv\Scripts\python -m scripts.gui_server` | Local web workbench: 3D viewer, command builder, job runner, prompt+image generation (see `docs/gui_guide.md`) |

CadQuery scripts are plain Python: `.venv\Scripts\python my_part.py`
(export with `cq.exporters.export(result, "part.stl")`).

---

## SDF toolkit in 60 seconds

```python
from scripts import sdf_kit as sk
from scripts import organic as og

# Primitives: sphere, box, rounded_box, cylinder, capsule, capped_cone,
#             cone_capsule, torus, ellipsoid, half_space, revolve_profile
# Ops:        union, intersect, subtract (+ smooth_ variants, blend in mm),
#             intersect_pruned (cheap envelope gates expensive interior)
# Modifiers:  translate, rotate, scale, offset, shell, displace, twist,
#             repeat_polar, mirror_x, warp (domain-warp: wavy organic edges)
# Noise:      sk.fbm_noise(amplitude, frequency, octaves, seed) -> displace
# Organic:    og.grow_branches(...)      antlers/trees/branching coral
#             og.organ_pipe_tubes(...)   tube clusters
#             og.skeleton_sdf(skel, blend) -> SDF from either of the above
#             og.taper_profile(base_r, top_r, height, curve) -> exact envelope
#             og.phyllotaxis_disk(n, r)  even points on a disk
# Voronoi:    og.revolved_sheet(profile)        unsigned sheet distance (no caps)
#             og.surface_points(profile, count) blue-noise cell seeds (+density)
#             og.voronoi_lattice(pts, sheet, strut_r)  round-strut open cells
#             -> worked example with rim/disk/twist: models/voronoi_funnel/

f = sk.smooth_union(2.5, sk.sphere(12), sk.sphere(9, center=(0, 0, 14)))
f = sk.displace(f, sk.fbm_noise(amplitude=0.5, frequency=0.15, seed=7))
m = sk.mesh(f, bounds=((-15, -15, -14), (15, 15, 26)), voxel=0.4,
            decimate_to=250_000)   # meshes are auto-welded: watertight
sk.save_stl(m, "blob.stl")         # survives STL round-trip, guaranteed
```

Full cookbook with recipes: `docs/organic_modeling.md`.
Worked exact-dimensions example: `models/organ_coral/`.

---

## Printability defaults (bake into every model)

- Min wall/feature: **1.2 mm** (FDM, 0.4 mm nozzle); min branch tip radius ~0.8 mm
- Flat bottom at z=0 for bed adhesion; avoid >45° unsupported overhangs where
  cheap to do so (near-vertical growth, taper *inward* going up)
- Mating parts: 0.2 mm clearance per side
- `hollow` creates sealed cavities — boolean-subtract a drain cylinder for
  resin printing
- Note the intended print orientation in spec.md

---

## Performance guide (SDF meshing)

| Situation | Setting |
|---|---|
| First look / iterating shape | `voxel_mm: 0.8`–`1.0` (seconds) |
| Final export, organic surfaces | `voxel_mm: 0.4`–`0.5` |
| Surface noise must be visible | voxel ≤ noise amplitude |
| Big STL (>20 MB) | pass `decimate_to=250_000` to `sk.mesh` |
| Hundreds of skeleton segments slow | keep `sk.mesh(block=48)` default; envelope-gate with `intersect_pruned` |
| Reference: organ_coral, 13.7 M voxels, ~500 segments | ~80 s end-to-end |

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `SDF is positive everywhere in bounds` | Bounds don't contain the model — check units/placement |
| bbox slightly smaller than spec | Bounds clipped the model (border capping) — grow bounds by 3×voxel |
| Validator says not watertight after my own mesh code | Use `sk.mesh` / `mesh_tools.weld` — raw marching-cubes output won't survive the float32 STL round-trip |
| Surface looks like gravel | Noise `frequency` too high or `voxel` too coarse |
| Tubes look like stacked beads | Too few path steps / too much wander — raise `steps`, lower `wander` |
| OpenSCAD output garbled / UnicodeEncodeError | Don't print `→`/`✓` to Windows consoles; ASCII only in CLI output |
| `cq` import slow first time | Normal (OCP loads ~5 s); subsequent imports are faster |

---

## Tier B: API-driven generation (optional, needs keys)

`scripts/generate.py` asks a hosted LLM to write OpenSCAD, CadQuery, or
SDF-toolkit code, then compiles + validates it. Pipelines: `openscad`
(mechanical), `cadquery` (precise B-rep), `sdf` (organic — the LLM writes
Python against `sdf_kit`/`organic`, run with the project root on PYTHONPATH,
and the `save_stl` target is rewritten into `output/stl/`). Current defaults
(2026-06): `anthropic` → `claude-opus-4-8`; `openai` → `gpt-5.5`; `google` →
`gemini-3.5-flash` (google-genai SDK); `ollama` → local, no key. Keys go in
`.env` (copy `.env.example`). Prompts live in `prompts/<pipeline>/`; the
`sdf` few-shot examples are verified runnable code — keep them that way.

`--image photo.jpg` (repeatable) attaches reference images the LLM actually
sees — supported on all four providers (Ollama needs a vision model like
`llama3.2-vision`). The GUI (`scripts.gui_server`) exposes all of this as
the "Generate from prompt" action with an image-upload field (files land in
`output/uploads/`) and previews the resulting STL in its viewer.

When *you* are the LLM, you don't need this tier — write the code directly
and use the toolbox above. Tier B exists for batch jobs
(`scripts/batch_generate.py`) and model comparisons.

---

## Repo layout

```
models/          one folder per model: spec.md + params.json + model.py + output/
models/_template self-documenting starting point — copy it
scripts/         all tooling (toolbox above) — importable package
templates/       known-good OpenSCAD + CadQuery reference parts
prompts/         system prompts / few-shot examples for Tier B
tools/openscad/  portable OpenSCAD 2025.08.04 + BOSL2 (gitignored; see setup guide)
docs/            setup_guide, organic_modeling cookbook, printing_guidelines, resources
stl_library/     curated, print-tested STLs (committed)
experiments/     scratch space (STLs gitignored)
output/          Tier B pipeline outputs (gitignored)
```
