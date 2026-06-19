# Resources & References

Curated list of repos, tools, and resources for LLM-based STL generation.
Last updated: 2026-06-09

---

## OpenSCAD + LLM Repos

| Repo | URL | Description | LLM | Notes |
|------|-----|-------------|-----|-------|
| **OpenSCAD Studio** | [GitHub](https://github.com/zacharyfmarion/openscad-studio) | Full IDE with AI copilot, MCP support, live 3D preview | BYOK (Claude/GPT) | Web + macOS app. [Demo](https://openscad-studio.pages.dev/) |
| **ClawSCAD** | [GitHub](https://github.com/levkropp/ClawSCAD) | AI CAD app with auto-iteration & checkpoint branching | Claude Code | Feeds render errors back to LLM automatically |
| **ScadLM** | [GitHub](https://github.com/KrishKrosh/ScadLM) | Agentic AI CAD with visual transformer feedback | Custom | Python backend + React frontend |
| **nl-cad** | [GitHub](https://github.com/Adam0Brien/nl-cad) | Natural language → OpenSCAD with BOSL2 library | LLM API | Great for mechanical parts (bolts, nuts, etc.) |
| **CAD-GPT** | [GitHub](https://github.com/BlueAsuka/CAD-GPT) | "Logic of generation" approach | GPT | Emphasizes human-in-the-loop |
| **TalkCAD** | [GitHub](https://github.com/ierror/talk-cad) | Conversational CAD with multi-agent architecture | Multi-agent | Orchestrator + Builder + Researcher agents |
| **SynapsCAD** | [GitHub](https://github.com/ierror/synaps-cad) | Rust-native AI CAD IDE (Bevy engine) | Claude/GPT/Ollama | No external OpenSCAD binary needed |
| **CadEval** | [GitHub](https://github.com/wgpatrick/cadeval) | Benchmark/eval framework for LLM → OpenSCAD | Any | Volume diff & chamfer distance metrics |
| **CADAM** | [GitHub](https://github.com/Adam-CAD/CADAM) | Browser-based text → OpenSCAD with parameter sliders | Any | [Live demo](https://adam.new/cadam). React/WASM/Three.js |
| **KachraCraft** | [GitHub](https://github.com/jonathanwalker/kachracraft) | Conversational 3D gen via SolidPython → OpenSCAD → STL | Claude (Bedrock) | Vue.js + Flask. Good pipeline reference |
| **3dmake** | [GitHub](https://github.com/tdeck/3dmake) | Non-visual 3D design tool with LLM integration | LLM API | CLI-focused OpenSCAD generation |

## MCP Servers for OpenSCAD

| Repo | URL | Description |
|------|-----|-------------|
| **OpenSCAD MCP Server** | [GitHub](https://github.com/jhacksman/OpenSCAD-MCP-Server) | Full MCP server with preview generation, multi-view |
| **openscad-mcp** (julianschill) | [GitHub](https://github.com/julianschill/openscad-mcp) | TypeScript MCP server for Claude Desktop |
| **openscad-mcp** (fboldo) | [GitHub](https://github.com/fboldo/openscad-mcp-server) | Uses OpenSCAD WASM, dependency-free |
| **openscad-mcp** (quellant) | [GitHub](https://github.com/quellant/openscad-mcp) | High-fidelity rendering focus |
| **openscad-mcp** (format37) | [GitHub](https://github.com/format37/openscad-mcp) | Script composition focus |

## CadQuery + LLM Repos

| Repo | URL | Description | LLM | Notes |
|------|-----|-------------|-----|-------|
| **Text2CAD** | [GitHub](https://github.com/khan-yusuf/Text2CAD) | Text → JSON IR → CadQuery code (two-stage) | GPT-4/Claude/Gemini | Great architecture pattern |
| **CQAsk** | [GitHub](https://github.com/OpenOrion/CQAsk) | Web UI for text → CadQuery | OpenAI | Simple and practical |
| **CAD-Coder** | [GitHub](https://github.com/anniedoris/CAD-Coder) | Image → CadQuery via fine-tuned VLM | LLaVA + Vicuna-13B | 100% syntactic validity reported |
| **CadQueryEval** | [GitHub](https://github.com/danwahl/cadqueryeval) | CadQuery generation benchmark | Any | Based on CadEval methodology |
| **3D-GPT** | [GitHub](https://github.com/zbruceli/3d-gpt) | Framework using LLMs to write CadQuery code | GPT | Simple text → CadQuery pipeline |
| **agentcad** ⭐ | [agentcad.dev](https://agentcad.dev) | CLI giving AI agents CAD skills — run → render → inspect → fix | Any (MCP) | Executes CadQuery/build123d, renders PNGs, validates. `pip install agentcad` |

## Local / Fine-Tuned Models

| Model | Access | Description |
|-------|--------|-------------|
| **C3D-v0** | `ollama pull joshuaokolo/C3Dv0` | Fine-tuned Gemma 3n (4B) on ~48K CadQuery examples. ~10GB RAM. Also: `npm install -g c3d` |
| **LLaMA-Mesh** | [GitHub](https://github.com/nv-tlabs/LLaMA-Mesh) | NVIDIA fine-tuned Llama 3.1 8B that outputs OBJ mesh data as text tokens |
| **MeshGen** | [GitHub](https://github.com/huggingface/meshgen) | Blender add-on for LLaMA-Mesh. Local or remote inference (8GB+ VRAM) |

## CAD Libraries & Tools

| Tool | URL | Description |
|------|-----|-------------|
| **OpenSCAD** | [openscad.org](https://openscad.org/) | Programmatic CSG modeling, CLI export to STL |
| **CadQuery** | [GitHub](https://github.com/CadQuery/cadquery) | Python BREP modeling (Apache 2.0) |
| **build123d** | [GitHub](https://github.com/gumyr/build123d) | Modern CadQuery alternative with cleaner API, same OpenCASCADE kernel |
| **SolidPython2** | [GitHub](https://github.com/jeff-dh/SolidPython) | Python wrapper for OpenSCAD (LGPL-2.1) |
| **BOSL2** | [GitHub](https://github.com/BelfrySCAD/BOSL2) | OpenSCAD library with threading, rounding, etc. |
| **Trimesh** | [trimesh.org](https://trimesh.org/) | Python mesh analysis/repair |
| **PyMeshFix** | [PyPI](https://pypi.org/project/pymeshfix/) | Automated watertight mesh repair |
| **ADMesh** | [GitHub](https://github.com/admesh/admesh) | CLI STL analysis and repair |

## Commercial / API Services

| Tool | URL | Key Feature |
|------|-----|-------------|
| **Zoo (KittyCAD)** ⭐ | [zoo.dev](https://zoo.dev) | Text-to-CAD API generating B-Rep STEP files. Python/TS/Rust SDKs. Free tier. |
| **PrintPal.io** | [printpal.io](https://printpal.io/) | Chat-driven agent, exports STL/3MF/STEP |
| **PromptSCAD** | [promptscad.com](https://promptscad.com/) | Lightweight text-to-SCAD |
| **ModelRift** | [modelrift.com](https://modelrift.com/) | Draw-on-screenshot corrections, version control |

## Curated Resource Lists

| Resource | URL | Description |
|----------|-----|-------------|
| **Awesome-LLM-3D** | [GitHub](https://github.com/ActiveVisionLab/Awesome-LLM-3D) | THE comprehensive curated list for LLM+3D papers/repos |
| **Awesome 3D Generation** | [awesome3dgen.com](https://awesome3dgen.com/) | Categorized by method (Mesh, NeRF, Gaussian Splatting) |

## Neural 3D Generation (Mesh-Based)

| Tool | URL | Notes |
|------|-----|-------|
| **Shap-E** | [GitHub](https://github.com/openai/shap-e) | OpenAI's text/image → 3D mesh (MIT). Not ideal for printing — outputs need cleanup. |

---

## Key Architecture Patterns

### 1. Generate → Render → Visual Feedback → Fix
Used by ClawSCAD, ModelRift, ScadLM. LLM generates code → OpenSCAD renders → screenshot/error fed back → LLM fixes. **Most effective for quality.**

### 2. MCP Server Integration
Used by OpenSCAD Studio, OpenSCAD MCP Server. AI agent connects via MCP → reads workspace, renders, edits. **Most future-proof.**

### 3. Two-Stage (Text → JSON IR → CAD Code)
Used by Text2CAD. Adds validation between stages. **Most robust for complex parts.**

### 4. Multi-Agent Architecture
Used by TalkCAD. Specialized agents handle different design aspects. **Best for complex workflows.**

### 5. Fine-Tuned Domain Models
Used by C3D-v0, CAD-Coder. Trade generality for domain expertise. **Best for offline/local use.**

---

## LLM Rankings for CAD Generation

Based on community consensus and benchmarks:

1. **Claude 3.5 Sonnet / Claude 4** — Best spatial reasoning and code quality
2. **GPT-4 / GPT-4o** — Strong all-around, most examples in the wild
3. **Gemini Pro** — Good for iterative refinement
4. **C3D-v0 (local)** — Best offline option for CadQuery specifically
5. **Local models (Ollama)** — Viable for simple parts with good prompts
