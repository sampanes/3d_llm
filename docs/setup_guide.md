# Setup Guide

Complete setup instructions for the 3D LLM project — from zero to your first AI-generated 3D model.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installing Python Dependencies](#installing-python-dependencies)
3. [Installing OpenSCAD](#installing-openscad)
4. [Installing CadQuery](#installing-cadquery)
5. [Setting Up API Keys](#setting-up-api-keys)
6. [Running Your First Generation](#running-your-first-generation)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- **Python 3.10+** — [Download](https://www.python.org/downloads/)
- **Git** — [Download](https://git-scm.com/downloads)
- A 3D printer slicer (recommended: [PrusaSlicer](https://www.prusa3d.com/prusaslicer/) or [Cura](https://ultimaker.com/software/ultimaker-cura/))
- At least one LLM API key (OpenAI, Anthropic, or Google)

---

## Installing Python Dependencies

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd 3d_llm
```

### 2. Create a Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

> [!NOTE]
> If `requirements.txt` doesn't exist yet, install the core packages manually:
> ```bash
> pip install openai anthropic google-generativeai
> pip install pyyaml rich httpx
> pip install numpy trimesh  # For STL validation
> ```

---

## Installing OpenSCAD

OpenSCAD is the primary target for LLM-generated 3D code. The system generates `.scad` files and calls OpenSCAD to render them to STL.

### Windows

1. Download the installer from [openscad.org/downloads](https://openscad.org/downloads.html)
2. Run the `.exe` installer
3. Add OpenSCAD to your PATH:
   - Default location: `C:\Program Files\OpenSCAD\openscad.exe`
   - Add `C:\Program Files\OpenSCAD` to your system PATH

### macOS

```bash
# Using Homebrew (recommended)
brew install --cask openscad

# Or download the .dmg from openscad.org/downloads
```

### Linux

```bash
# Ubuntu / Debian
sudo apt install openscad

# Fedora
sudo dnf install openscad

# Arch
sudo pacman -S openscad

# Or use the AppImage from openscad.org/downloads
```

### Verify Installation

```bash
openscad --version
# Expected output: OpenSCAD version 2024.xx.xx
```

> [!IMPORTANT]
> The project calls OpenSCAD in headless mode (`openscad -o output.stl input.scad`). Make sure the `openscad` command is accessible from your terminal.

---

## Installing CadQuery

CadQuery is an alternative backend that produces more complex geometry via Python scripting.

### Option A: pip install (Recommended)

```bash
pip install cadquery
```

### Option B: Conda (if pip fails)

CadQuery depends on OCP (OpenCascade), which can be tricky to build. Conda provides pre-built binaries:

```bash
conda install -c cadquery -c conda-forge cadquery
```

### Option C: CQ-editor (GUI for previewing)

For interactive development and previewing CadQuery models:

```bash
# Install CQ-editor (optional but very helpful)
pip install cq-editor
```

Or download from [CQ-editor releases](https://github.com/CadQuery/CQ-editor/releases).

### Verify Installation

```python
python -c "import cadquery as cq; print('CadQuery', cq.__version__, 'OK')"
```

> [!TIP]
> If you only plan to use the OpenSCAD pipeline, CadQuery installation is optional. The system will fall back gracefully.

---

## Setting Up API Keys

### Create a `.env` File

Copy the example environment file and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```env
# At least one of these is required
OPENAI_API_KEY=sk-...your-openai-key...
ANTHROPIC_API_KEY=sk-ant-...your-anthropic-key...
GOOGLE_API_KEY=AI...your-google-key...

# Optional: for local models via Ollama
OLLAMA_BASE_URL=http://localhost:11434
```

### Where to Get API Keys

| Provider   | URL                                              | Free Tier?       |
|------------|--------------------------------------------------|------------------|
| OpenAI     | [platform.openai.com](https://platform.openai.com/api-keys) | No (pay-as-you-go) |
| Anthropic  | [console.anthropic.com](https://console.anthropic.com/)      | Limited credits    |
| Google     | [aistudio.google.com](https://aistudio.google.com/apikey)    | Generous free tier |
| Ollama     | [ollama.com](https://ollama.com/)                             | Free (local)       |

> [!CAUTION]
> Never commit your `.env` file to version control. The `.gitignore` should already exclude it. Double-check before pushing.

### For Ollama (Local Models)

```bash
# Install Ollama
# Windows: download from ollama.com
# macOS: brew install ollama
# Linux: curl -fsSL https://ollama.com/install.sh | sh

# Pull a capable code model
ollama pull codellama:34b
# or
ollama pull deepseek-coder:33b
```

---

## Running Your First Generation

### Quick Test — OpenSCAD Pipeline

```bash
python main.py generate \
  --prompt "A small box 50x30x20mm with rounded corners" \
  --pipeline openscad \
  --output output/scad/my_first_box.scad
```

This will:
1. Send the prompt to the configured LLM
2. Extract the OpenSCAD code from the response
3. Validate the code syntax
4. Save the `.scad` file
5. Optionally render to STL via OpenSCAD

### Quick Test — CadQuery Pipeline

```bash
python main.py generate \
  --prompt "A phone stand with 60 degree viewing angle" \
  --pipeline cadquery \
  --output output/stl/phone_stand.stl
```

### Batch Generation

```bash
python main.py batch --file batch_jobs/example_batch.yaml
```

### Preview a Generated File

```bash
# Open in OpenSCAD GUI
openscad output/scad/my_first_box.scad

# Or render to STL from command line
openscad -o output/stl/my_first_box.stl output/scad/my_first_box.scad
```

---

## Troubleshooting

### "openscad" is not recognized

**Cause:** OpenSCAD is not in your system PATH.

**Fix (Windows):**
1. Find the OpenSCAD install directory (usually `C:\Program Files\OpenSCAD`)
2. Add it to PATH: Settings → System → Advanced → Environment Variables → Edit PATH
3. Restart your terminal

**Fix (macOS):**
```bash
# If installed via .dmg, create a symlink:
sudo ln -s /Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD /usr/local/bin/openscad
```

### CadQuery import error: "No module named OCP"

**Cause:** The OpenCascade bindings didn't install correctly via pip.

**Fix:**
```bash
pip uninstall cadquery
conda install -c cadquery -c conda-forge cadquery
```

### API key errors / 401 Unauthorized

- Double-check your `.env` file has the correct key
- Ensure the key is active and has available credits
- Try the key directly with `curl`:
  ```bash
  curl https://api.openai.com/v1/models \
    -H "Authorization: Bearer sk-your-key-here"
  ```

### Generated code has syntax errors

This is expected sometimes — LLMs aren't perfect with 3D code. The system has built-in validation and retry logic. If it persists:

1. Try a different LLM (Claude tends to produce cleaner OpenSCAD)
2. Simplify your prompt
3. Use a template as a starting point (see `templates/`)

### STL has non-manifold geometry / slicer warns about errors

```bash
# Use the built-in mesh repair (if available)
python main.py repair output/stl/broken_model.stl

# Or use an external tool
# Meshmixer (free): Import → Edit → Inspector → Auto Repair
# Netfabb (free online): netfabb.com
```

### OpenSCAD renders but produces empty/invisible geometry

Common causes:
- Dimensions are 0 or negative
- Objects are subtracted before being added (order of operations)
- `$fn` is too low for small features

**Fix:** Open the `.scad` file in OpenSCAD GUI and use `F5` (preview) to debug.

### Out of memory during OpenSCAD render

High `$fn` values with complex `minkowski()` operations can consume gigabytes of RAM.

**Fix:**
- Reduce `$fn` to 30–60
- Replace `minkowski()` with `hull()` where possible
- Break complex models into parts

---

## Next Steps

- Read the [LLM Comparison Guide](llm_comparison.md) to choose the best model for your use case
- Review [Printing Guidelines](printing_guidelines.md) before sending AI-generated models to your printer
- Explore the templates in `templates/` for reference geometry
- Try the example batch job in `batch_jobs/example_batch.yaml`
