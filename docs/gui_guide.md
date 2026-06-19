# 3D LLM Workbench — GUI guide for new users

The GUI is a local web app that wraps every command-line tool in this repo:
build models, validate and preview STLs, edit meshes, and generate brand-new
models from a text prompt (optionally plus a reference photo). It never does
anything the CLI can't — it just shows you the exact command before running
it, so you learn the CLI for free.

## 1. Start it

```cmd
cd C:\path\to\3d_llm
.venv\Scripts\python -m scripts.gui_server
```

Open **http://127.0.0.1:8765/** in any browser. If the port is busy, add
`--port 9000` (any free number) and open that instead. Stop the server with
`Ctrl+C` in the console window.

## 2. The screen, left to right

- **Model folders** — every `models/<name>/` with a `model.py`. Pick one and
  use the *Build model* action to regenerate it from its `params.json`.
- **Mesh files** — every STL under `models/`, `output/`, `experiments/`,
  `stl_library/`. The search box filters by path. Selecting one loads it in
  the viewer and becomes the input for mesh actions.
- **3D viewer** — drag to orbit, mouse wheel to zoom, `Iso / Front / Right /
  Top` buttons to snap views. **Open in 3D Builder** opens the selected STL
  in your Windows default 3D app. The caption shows real dimensions in mm
  and triangle count.
- **Action panel** (right) — choose what to run. Every field has hover help:
  rest your mouse on anything for a second or two. The **Help** button (top
  right) opens a longer overview.
- **Command preview** — the exact command line the Run button will execute,
  with a plain-English line per flag. You can copy it and run it yourself in
  cmd later; the GUI has no magic.
- **Job output** — live console output of the running job. Long jobs (SDF
  meshing, builds) stream their progress here; **Cancel** kills the job.

## 3. Generate a model from a prompt (the fun one)

Pick **Generate from prompt (LLM)** in the Action dropdown.

### One-time setup: API key

Hosted providers need a key in `.env` (the GUI shows `(no key in .env)` next
to providers that aren't configured):

```cmd
cd C:\path\to\3d_llm
copy .env.example .env
notepad .env
```

Paste in `ANTHROPIC_API_KEY=sk-ant-...` (or an OpenAI/Google key), save, and
restart the GUI server. **Ollama** needs no key — install it from
ollama.com, `ollama pull` a model, and pick provider `ollama`.

### Fill in the form

| Field | What to do |
|---|---|
| **Describe the model** | Plain language. Give hard dimensions ("14 x 5 inch base", "120 mm tall") — inches are fine, the LLM converts. Name the *style*: "voronoi lattice shell", "branching coral", "organ-pipe tubes", "twisted vase". |
| **Reference image** | Optional but powerful: attach a photo of a print or object you want recreated. The LLM *sees* it — form, proportions, cell structure — and combines it with your text. (On Ollama this needs a vision model such as `llama3.2-vision`.) |
| **Pipeline** | `sdf` for organic/grown/lattice shapes, `openscad` for boxes/brackets/mechanical, `cadquery` for precise filleted parts. |
| **Provider / Model** | Provider picks the company; Model overrides the exact model id (blank = a good default). |
| **Few-shot examples** | Leave ON. It adds verified worked examples to the request — markedly better geometry for a few more tokens. |
| **Temperature** | 0.7 default. Lower = more predictable, higher = more adventurous. |

Press **Run**. The job streams progress; an `sdf` build can take one to a
few minutes (meshing at fine voxel size is the slow part — that's normal).
When it succeeds the new STL is auto-selected in the viewer.

### Where things land

- Generated source code: `output\sdf\` (or `output\scad\`, `output\cadquery\`)
- Final STL: `output\stl\`
- Uploaded reference images: `output\uploads\`

The source file is the real product: you can open it, tweak a number, and
re-run it by hand for free, instead of paying for another LLM call:

```cmd
set PYTHONPATH=C:\path\to\3d_llm
.venv\Scripts\python output\sdf\my_model_20260612_120000.py
```

## 4. The other actions, in one line each

- **Build model** — runs a `models/<name>/` folder end-to-end (generate →
  validate → preview PNGs → report). The reproducible path.
- **Validate** — watertightness/volume/bbox report for any STL; `Attempt
  repair` writes a fixed copy.
- **Render PNG preview** — contact-sheet image of a mesh (good for sharing).
- **Edit ▸ scale / rotate / hollow / boolean / cut / decimate / smooth /
  convert** — mesh surgery on any STL, no source code needed. E.g. *scale →
  To Z = 120* resizes a model to exactly 120 mm tall.

## 5. Tips and tricks

- **Hover anything.** Every field, flag, and checkbox explains itself after
  a moment.
- **Iterate cheap.** For model folders, set `voxel_mm` to 0.8–1.0 in
  `params.json` while you experiment (builds in seconds), then 0.4–0.5 for
  the final export (a minute or two).
- **Copy a worked example instead of starting blank.** `models/organ_coral/`
  (tube coral with exact dimensions) and `models/voronoi_funnel/` (twisted
  open-cell voronoi vase, recreated from a photo) are both real, verified
  models — copy the folder, rename, edit `params.json`, hit Build model.
- **Prompts: dimensions + style words + printability.** "watertight", "flat
  base for printing", "struts at least 3 mm" all steer the code generator.
- **A failed generate run still saves the source code** — check
  `output\sdf\`, the bug is often one number.
- **The command preview is a teaching tool.** Anything the GUI does, you can
  paste into cmd and script yourself later.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| Provider shows `(no key in .env)` | Create `.env` (section 3) and restart the server. |
| Job fails instantly with `ANTHROPIC_API_KEY not set` | Same as above — the key is missing or the server started before you saved it. |
| `Ollama call failed - is Ollama running?` | Start Ollama, and check the model is pulled: `ollama list`. |
| Reference image upload fails | Only png/jpg/jpeg/webp/gif, max 20 MB. |
| Viewer says "Static preview mode" | WebGL is off in that browser; the GUI falls back to PNG previews. Chrome/Edge default settings work. |
| Generate succeeded but the shape is wrong | Edit the saved source in `output\sdf\` and re-run it by hand, or re-prompt with more specific dimensions/style words, or attach a reference image. |
| Port already in use | `.venv\Scripts\python -m scripts.gui_server --port 9001` |
| SDF job seems stuck for minutes | Look at Job output — if it printed the `[sdf_kit] grid ...` line it's meshing; fine voxels legitimately take minutes. Cancel if you must. |
