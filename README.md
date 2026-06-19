# 3D LLM — AI-Assisted STL Generation for 3D Printing

Use various LLMs to reliably generate 3D-printable STL files through programmatic CAD pipelines (OpenSCAD and CadQuery). Instead of prompting an LLM for raw mesh data, this project asks models to write **CAD code** — OpenSCAD scripts or CadQuery Python — which is then compiled into watertight, printable STL files. The result is a repeatable, validated pipeline from natural-language description to physical print.

---

## Directory Structure

```
3d_llm/
├── README.md
├── AGENTS.md                 # Canonical model-building workflow (read this)
├── requirements.txt
├── setup.py
├── .env.example
├── prompts/                  # System prompts & few-shot examples
│   ├── openscad/             #   system_prompt.md, few_shot_examples.md, tips.md
│   ├── cadquery/             #   system_prompt.md, few_shot_examples.md, tips.md
│   ├── sdf/                  #   system_prompt.md, few_shot_examples.md, tips.md
│   └── meta_prompts.md       # Prompts for prompt refinement
├── scripts/                  # All tooling (importable package)
│   ├── generate.py           #   Tier B: LLM-driven generation pipeline
│   ├── batch_generate.py     #   Batch generation from a YAML/JSON job file
│   ├── llm_clients.py        #   Unified OpenAI/Anthropic/Google/Ollama wrapper
│   ├── build_model.py        #   Run a models/<name>/ folder end-to-end
│   ├── openscad_runner.py    #   OpenSCAD CLI wrapper (Manifold backend)
│   ├── sdf_kit.py            #   SDF toolkit (organic shapes)
│   ├── organic.py            #   Skeletons, branches, voronoi lattices
│   ├── edit_stl.py           #   Mesh surgery (scale/hollow/cut/boolean/...)
│   ├── mesh_tools.py         #   Shared mesh helpers (weld, IO, info)
│   ├── mesh_preview.py       #   Contact-sheet PNG of any mesh
│   ├── render_preview.py     #   Preview rendering helpers
│   ├── validate_stl.py       #   STL validation & light repair
│   └── gui_server.py         #   Local web workbench
├── models/                   # One folder per model: spec.md + params.json + model.py
│   └── _template/            #   Self-documenting starting point — copy it
├── templates/                # Known-good OpenSCAD + CadQuery reference parts
│   ├── openscad/
│   └── cadquery/
├── output/                   # Tier B pipeline outputs (gitignored)
│   ├── scad/  cadquery/  sdf/  stl/
│   ├── previews/  reports/
│   └── uploads/              #   GUI reference-image uploads
├── stl_library/              # Curated, print-tested STLs (committed)
├── experiments/              # Scratch space (STLs gitignored)
├── tests/                    # Unit tests (run: python -m unittest discover -s tests)
├── tools/openscad/           # Portable OpenSCAD + BOSL2 (gitignored; see setup_guide)
└── docs/                     # setup_guide, organic_modeling, printing_guidelines, ...
```

---

## Prerequisites

| Dependency       | Version | Purpose                              |
| ---------------- | ------- | ------------------------------------ |
| **Python**       | 3.11    | Runtime (tested on 3.11)             |
| **OpenSCAD**     | 2024+   | Compile `.scad` → `.stl` (SCAD pipeline) |
| **CadQuery**     | 2.4+    | Programmatic CAD in Python (CQ pipeline) |

> [!NOTE]
> You only need the backend(s) you plan to use. If you only care about the OpenSCAD pipeline, CadQuery is optional — and vice versa.

---

## Quick Start

### Local GUI

```powershell
.venv\Scripts\python -m scripts.gui_server
```

Open `http://127.0.0.1:8765/`. The GUI is a thin wrapper around the repo
scripts: it shows the exact command and flags before running builds,
validation, previews, and mesh edits. It includes a live 3D viewer for any
STL in the project, an "Open in 3D Builder" button, and a
**Generate from prompt** action that drives `scripts.generate` (pick the
`sdf` pipeline for organic coral/bone/grown shapes — needs an API key in
`.env`, or a local Ollama). You can also attach a **reference image** the
LLM sees alongside your text (e.g. a photo of a print to recreate).
New-user walkthrough with tips: `docs/gui_guide.md`.

### CLI setup

```bash
# 1. Clone the repo
git clone <repo-url> 3d_llm
cd 3d_llm

# 2. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt
pip install -e .              # Editable install so scripts/ is importable

# 4. Set up API keys
copy .env.example .env        # Windows
# cp .env.example .env        # macOS / Linux
# Then edit .env with your API keys

# 5. Generate your first STL (run as a module so `scripts/` imports resolve)
python -m scripts.generate --prompt "A small box with a lid" --pipeline openscad
```

---

## Supported LLMs

Current defaults (2026-06; override per call with `--model`, or `DEFAULT_MODEL` in `.env`):

| Provider              | Default model            | Env Variable           |
| --------------------- | ------------------------ | ---------------------- |
| **OpenAI**            | `gpt-5.5`                | `OPENAI_API_KEY`       |
| **Anthropic**         | `claude-opus-4-8`        | `ANTHROPIC_API_KEY`    |
| **Google**            | `gemini-3.5-flash` (google-genai SDK) | `GOOGLE_API_KEY` |
| **Local (Ollama)**    | `qwen2.5-coder:14b`      | n/a (runs locally)     |

---

## Key Resources

- [OpenSCAD Documentation](https://openscad.org/documentation.html)
- [CadQuery Documentation](https://cadquery.readthedocs.io/)
- [SolidPython2 (Python → OpenSCAD)](https://github.com/jeff-dh/SolidPython)
- [trimesh (STL analysis)](https://trimesh.org/)
- [Ollama (local models)](https://ollama.com/)

---

## License

Private project — not yet published.
