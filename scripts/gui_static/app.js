const els = {
  rootPath: document.getElementById("rootPath"),
  helpBtn: document.getElementById("helpBtn"),
  closeHelpBtn: document.getElementById("closeHelpBtn"),
  helpDrawer: document.getElementById("helpDrawer"),
  helpScrim: document.getElementById("helpScrim"),
  helpTip: document.getElementById("helpTip"),
  refreshBtn: document.getElementById("refreshBtn"),
  copyCommandBtn: document.getElementById("copyCommandBtn"),
  modelSelect: document.getElementById("modelSelect"),
  meshSearch: document.getElementById("meshSearch"),
  meshSelect: document.getElementById("meshSelect"),
  meshBSelect: document.getElementById("meshBSelect"),
  actionSelect: document.getElementById("actionSelect"),
  optionsPanel: document.getElementById("optionsPanel"),
  commandLine: document.getElementById("commandLine"),
  flagList: document.getElementById("flagList"),
  commandStatus: document.getElementById("commandStatus"),
  runBtn: document.getElementById("runBtn"),
  cancelBtn: document.getElementById("cancelBtn"),
  jobOutput: document.getElementById("jobOutput"),
  jobMeta: document.getElementById("jobMeta"),
  viewerStats: document.getElementById("viewerStats"),
  openExternalBtn: document.getElementById("openExternalBtn"),
  canvas: document.getElementById("meshCanvas")
};

const app = {
  data: { models: [], meshes: [] },
  commandInfo: null,
  currentJob: null,
  pollTimer: null,
  commandTimer: null,
  helpTimer: null
};

function showFatalUiError(message) {
  if (els.jobOutput) {
    els.jobOutput.textContent = `FRONTEND ERROR: ${message}`;
  }
  if (els.jobMeta) {
    els.jobMeta.textContent = "frontend error";
  }
}

window.addEventListener("error", (event) => {
  // Benign Chrome layout-loop warning, not a real failure.
  if (event.message && event.message.includes("ResizeObserver loop")) return;
  showFatalUiError(event.message || "unknown error");
});
window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason && (event.reason.message || String(event.reason));
  showFatalUiError(reason || "unhandled promise rejection");
});

// `viewer` is created at the bottom of this file: MeshViewer/FallbackViewer
// prototype methods are assigned after their declarations, so constructing
// one here would see a half-built prototype and always fail.
let viewer = null;

const optionHelp = {
  skip_preview: "Omits mesh_preview PNG rendering after model.py finishes.",
  skip_validation: "Omits validate_stl checks after model.py writes STLs.",
  timeout: "Maximum seconds to let model.py run before build_model stops it.",
  json: "Adds --json so validate_stl prints a machine-readable report.",
  fix: "Adds --fix for trimesh light repair before writing an output mesh.",
  output: "Adds -o/--output. Leave blank to use the script's default output name.",
  views: "Comma-separated view panels for scripts.mesh_preview, such as iso,front,right,top.",
  size: "Pixel size for each generated preview panel.",
  color: "Mesh material color used by scripts.mesh_preview PNG rendering.",
  separate: "Writes one PNG per view instead of one contact sheet.",
  no_grid: "Hides the dimension grid in generated PNG previews.",
  force_remesh: "Skips light repair and goes directly to voxel remeshing.",
  voxel: "Voxel size in millimeters. Smaller preserves more detail but costs more time and memory.",
  no_center: "Drops the mesh to Z=0 without recentering X/Y.",
  factor: "Uniform scale multiplier.",
  to_x: "Uniformly scale until the X bounding-box size matches this millimeter value.",
  to_y: "Uniformly scale until the Y bounding-box size matches this millimeter value.",
  to_z: "Uniformly scale until the Z bounding-box size matches this millimeter value.",
  stretch: "Allows non-uniform scaling when more than one target dimension is set.",
  axis: "Axis used by rotate.",
  angle: "Rotation angle in degrees.",
  x: "Translation offset along X in millimeters.",
  y: "Translation offset along Y in millimeters.",
  z: "Translation offset along Z in millimeters.",
  wall: "Wall thickness in millimeters for hollowing.",
  boolean_op: "Boolean operation: union combines, difference subtracts mesh B from mesh A, intersection keeps overlap.",
  cut_axis: "Axis normal for the planar cut.",
  cut_value: "Plane position along the selected axis, in millimeters.",
  keep: "Which side of the cut plane survives.",
  no_cap: "Leaves the cut face open instead of capping it.",
  ratio: "Fraction of triangles to keep during decimation.",
  faces: "Exact target triangle count. If set, it overrides ratio.",
  iterations: "Number of Taubin smoothing passes.",
  prompt: "Plain-language description of the model. Give hard dimensions (inches are fine, they get converted to mm) and the look you want.",
  image: "Optional reference photo or render. The LLM actually sees it (form, proportions, surface structure) and combines it with your text. On Ollama this needs a vision model such as llama3.2-vision.",
  pipeline: "openscad suits boxes/brackets/mechanical parts, cadquery suits precise filleted parts, sdf suits organic coral/bone/grown shapes.",
  llm: "Which hosted LLM writes the modeling code. Providers marked 'no key' need an API key in .env first (copy .env.example).",
  llm_model: "Optional exact model id, e.g. claude-opus-4-8. Leave blank for the provider default.",
  few_shot: "Adds worked examples to the request. Slower and more tokens, usually better geometry.",
  temperature: "LLM sampling temperature. Lower is more deterministic.",
  max_tokens: "Token budget for the generated code.",
};

function api(path, options = {}) {
  const init = { ...options };
  if (init.body && typeof init.body !== "string") {
    init.body = JSON.stringify(init.body);
    init.headers = { "Content-Type": "application/json", ...(init.headers || {}) };
  }
  return fetch(path, init).then(async (res) => {
    const type = res.headers.get("Content-Type") || "";
    const body = type.includes("application/json") ? await res.json() : await res.text();
    if (!res.ok) {
      throw new Error(body.error || body || `HTTP ${res.status}`);
    }
    return body;
  });
}

function setBadge(text, kind = "neutral") {
  els.commandStatus.textContent = text;
  els.commandStatus.className = `badge ${kind}`;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function meshLabel(mesh) {
  return `${mesh.path}  (${formatBytes(mesh.size_bytes)})`;
}

function renderModels() {
  els.modelSelect.innerHTML = "";
  for (const model of app.data.models) {
    const opt = document.createElement("option");
    opt.value = model.path;
    opt.textContent = model.name;
    els.modelSelect.appendChild(opt);
  }
}

function renderMeshes(keepValue = true) {
  const previous = keepValue ? els.meshSelect.value : "";
  const previousB = keepValue ? els.meshBSelect.value : "";
  const query = els.meshSearch.value.trim().toLowerCase();
  const meshes = app.data.meshes.filter((mesh) => mesh.path.toLowerCase().includes(query));

  els.meshSelect.innerHTML = "";
  els.meshBSelect.innerHTML = "";
  for (const mesh of meshes) {
    const opt = document.createElement("option");
    opt.value = mesh.path;
    opt.textContent = meshLabel(mesh);
    els.meshSelect.appendChild(opt);
  }
  for (const mesh of app.data.meshes) {
    const opt = document.createElement("option");
    opt.value = mesh.path;
    opt.textContent = mesh.path;
    els.meshBSelect.appendChild(opt);
  }

  if (previous && [...els.meshSelect.options].some((o) => o.value === previous)) {
    els.meshSelect.value = previous;
  }
  if (!els.meshSelect.value && els.meshSelect.options.length) {
    els.meshSelect.selectedIndex = 0;
  }
  if (previousB && [...els.meshBSelect.options].some((o) => o.value === previousB)) {
    els.meshBSelect.value = previousB;
  }
  if (!els.meshBSelect.value && els.meshBSelect.options.length) {
    els.meshBSelect.selectedIndex = Math.min(1, els.meshBSelect.options.length - 1);
  }
}

async function loadState(keepSelections = true) {
  app.data = await api("/api/state");
  els.rootPath.textContent = app.data.root;
  renderModels();
  renderMeshes(keepSelections);
  renderOptions();
  await loadSelectedMesh();
  refreshCommandSoon();
}

function selectedMesh() {
  return els.meshSelect.value || (app.data.meshes[0] && app.data.meshes[0].path) || "";
}

async function loadSelectedMesh() {
  const path = selectedMesh();
  if (!path) {
    viewer.clear("No mesh loaded");
    return;
  }
  const mesh = app.data.meshes.find((item) => item.path === path) || null;
  try {
    await viewer.load(`/api/file?path=${encodeURIComponent(path)}&t=${Date.now()}`, path, mesh);
  } catch (err) {
    viewer.clear(`Viewer error: ${err.message}`);
  }
}

function actionParts() {
  const value = els.actionSelect.value;
  if (value.startsWith("edit:")) {
    return { action: "edit", operation: value.split(":")[1] };
  }
  return { action: value, operation: null };
}

function optionSpecs() {
  const { action, operation } = actionParts();
  if (action === "build_model") {
    return [
      { key: "skip_preview", label: "Skip preview", type: "bool", help: optionHelp.skip_preview },
      { key: "skip_validation", label: "Skip validation", type: "bool", help: optionHelp.skip_validation },
      { key: "timeout", label: "Timeout", type: "number", value: 900, min: 30, step: 30, help: optionHelp.timeout }
    ];
  }
  if (action === "generate") {
    const providers = app.data.providers || {};
    const provChoices = ["anthropic", "openai", "google", "ollama"].map((name) => ({
      value: name,
      label: providers[name] === false ? `${name} (no key in .env)` : name
    }));
    return [
      {
        key: "prompt", label: "Describe the model", type: "textarea", wide: true, rows: 5,
        placeholder: "e.g. an organic shape like a triangular prism built from coral/skeleton frameworks, 14 x 5 inch base rising to a horizontal 14 inch top edge, rounded slightly, struts about pencil thickness",
        help: optionHelp.prompt
      },
      {
        key: "image", label: "Reference image", type: "file",
        accept: ".png,.jpg,.jpeg,.webp,.gif", help: optionHelp.image
      },
      {
        key: "pipeline", label: "Pipeline", type: "select", value: "openscad",
        choices: [
          { value: "openscad", label: "openscad - boxes, brackets, mechanical" },
          { value: "cadquery", label: "cadquery - precise, fillets" },
          { value: "sdf", label: "sdf - organic, coral, grown" }
        ],
        help: optionHelp.pipeline
      },
      { key: "llm", label: "Provider", type: "select", value: "anthropic", choices: provChoices, help: optionHelp.llm },
      { key: "model", label: "Model", type: "text", placeholder: "provider default", help: optionHelp.llm_model },
      { key: "few_shot", label: "Few-shot examples", type: "bool", value: true, help: optionHelp.few_shot },
      { key: "temperature", label: "Temperature", type: "number", value: 0.7, min: 0, max: 2, step: 0.1, help: optionHelp.temperature },
      { key: "max_tokens", label: "Max tokens", type: "number", value: 8192, min: 256, step: 256, help: optionHelp.max_tokens },
      { key: "skip_validation", label: "Skip validation", type: "bool", help: optionHelp.skip_validation }
    ];
  }
  if (action === "validate") {
    return [
      { key: "json", label: "JSON output", type: "bool", value: true, help: optionHelp.json },
      { key: "fix", label: "Attempt repair", type: "bool", help: optionHelp.fix },
      { key: "output", label: "Repair output", type: "text", wide: true, placeholder: "optional .stl path", help: optionHelp.output }
    ];
  }
  if (action === "mesh_preview") {
    return [
      { key: "views", label: "Views", type: "text", value: "iso,front,right,top", wide: true, help: optionHelp.views },
      { key: "size", label: "Panel size", type: "number", value: 640, min: 160, step: 80, help: optionHelp.size },
      { key: "color", label: "Color", type: "color", value: "#cfc4a7", help: optionHelp.color },
      { key: "separate", label: "Separate files", type: "bool", help: optionHelp.separate },
      { key: "no_grid", label: "No grid", type: "bool", help: optionHelp.no_grid },
      { key: "output", label: "PNG output", type: "text", wide: true, placeholder: "optional .png path", help: optionHelp.output }
    ];
  }
  const commonOutput = { key: "output", label: "Output", type: "text", wide: true, placeholder: "optional output path", help: optionHelp.output };
  const specs = {
    repair: [
      { key: "force_remesh", label: "Force remesh", type: "bool", help: optionHelp.force_remesh },
      { key: "voxel", label: "Voxel", type: "number", step: 0.05, placeholder: "auto", help: optionHelp.voxel },
      commonOutput
    ],
    remesh: [
      { key: "voxel", label: "Voxel", type: "number", step: 0.05, placeholder: "auto", help: optionHelp.voxel },
      commonOutput
    ],
    place: [
      { key: "no_center", label: "Keep XY", type: "bool", help: optionHelp.no_center },
      commonOutput
    ],
    scale: [
      { key: "factor", label: "Factor", type: "number", step: 0.05, placeholder: "optional", help: optionHelp.factor },
      { key: "to_x", label: "To X", type: "number", step: 0.1, placeholder: "mm", help: optionHelp.to_x },
      { key: "to_y", label: "To Y", type: "number", step: 0.1, placeholder: "mm", help: optionHelp.to_y },
      { key: "to_z", label: "To Z", type: "number", step: 0.1, placeholder: "mm", help: optionHelp.to_z },
      { key: "stretch", label: "Stretch", type: "bool", help: optionHelp.stretch },
      commonOutput
    ],
    rotate: [
      { key: "axis", label: "Axis", type: "select", value: "z", choices: ["x", "y", "z"], help: optionHelp.axis },
      { key: "angle", label: "Angle", type: "number", value: 90, step: 1, help: optionHelp.angle },
      commonOutput
    ],
    translate: [
      { key: "x", label: "X", type: "number", value: 0, step: 0.1, help: optionHelp.x },
      { key: "y", label: "Y", type: "number", value: 0, step: 0.1, help: optionHelp.y },
      { key: "z", label: "Z", type: "number", value: 0, step: 0.1, help: optionHelp.z },
      commonOutput
    ],
    hollow: [
      { key: "wall", label: "Wall", type: "number", value: 2.0, step: 0.1, help: optionHelp.wall },
      { key: "voxel", label: "Voxel", type: "number", step: 0.05, placeholder: "auto", help: optionHelp.voxel },
      commonOutput
    ],
    boolean: [
      { key: "boolean_op", label: "Boolean", type: "select", value: "union", choices: ["union", "difference", "intersection"], help: optionHelp.boolean_op },
      commonOutput
    ],
    cut: [
      { key: "cut_axis", label: "Axis", type: "select", value: "z", choices: ["x", "y", "z"], help: optionHelp.cut_axis },
      { key: "cut_value", label: "Position", type: "number", value: 0, step: 0.1, help: optionHelp.cut_value },
      { key: "keep", label: "Keep", type: "select", value: "below", choices: ["below", "above"], help: optionHelp.keep },
      { key: "no_cap", label: "No cap", type: "bool", help: optionHelp.no_cap },
      commonOutput
    ],
    decimate: [
      { key: "ratio", label: "Ratio", type: "number", value: 0.5, min: 0.01, max: 1, step: 0.05, help: optionHelp.ratio },
      { key: "faces", label: "Faces", type: "number", step: 1000, placeholder: "optional", help: optionHelp.faces },
      commonOutput
    ],
    smooth: [
      { key: "iterations", label: "Iterations", type: "number", value: 10, min: 1, step: 1, help: optionHelp.iterations },
      commonOutput
    ],
    convert: [
      { key: "output", label: "Output", type: "text", wide: true, placeholder: "experiments/_gui/mesh.3mf", help: "Required target path. The extension chooses the output format." }
    ]
  };
  return specs[operation] || [];
}

function renderOptions() {
  els.optionsPanel.innerHTML = "";
  for (const spec of optionSpecs()) {
    const wrap = document.createElement("div");
    if (spec.help) wrap.dataset.help = spec.help;
    if (spec.wide || spec.type === "bool") wrap.classList.add(spec.type === "bool" ? "check-row" : "option-wide");

    if (spec.type === "bool") {
      const input = document.createElement("input");
      input.type = "checkbox";
      input.id = `opt_${spec.key}`;
      input.dataset.key = spec.key;
      if (spec.help) input.dataset.help = spec.help;
      input.checked = Boolean(spec.value);
      const label = document.createElement("label");
      label.setAttribute("for", input.id);
      if (spec.help) label.dataset.help = spec.help;
      label.textContent = spec.label;
      wrap.append(input, label);
    } else if (spec.type === "file") {
      // A file picker that uploads immediately; the command only ever sees
      // the project-relative path stored in the hidden input.
      wrap.classList.add("option-wide");
      const label = document.createElement("label");
      label.textContent = spec.label;
      const hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.id = `opt_${spec.key}`;
      hidden.dataset.key = spec.key;
      const picker = document.createElement("input");
      picker.type = "file";
      if (spec.accept) picker.accept = spec.accept;
      if (spec.help) picker.dataset.help = spec.help;
      const status = document.createElement("span");
      status.className = "file-status";
      const idleText = "optional - the LLM will see this image alongside your prompt";
      status.textContent = idleText;
      picker.addEventListener("change", async () => {
        const file = picker.files && picker.files[0];
        if (!file) {
          hidden.value = "";
          status.textContent = idleText;
          refreshCommandSoon();
          return;
        }
        status.textContent = `uploading ${file.name}...`;
        try {
          const dataUrl = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(new Error(`could not read ${file.name}`));
            reader.readAsDataURL(file);
          });
          const res = await api("/api/upload", {
            method: "POST",
            body: { filename: file.name, data: dataUrl }
          });
          hidden.value = res.path;
          status.textContent = `attached: ${res.path}`;
        } catch (err) {
          hidden.value = "";
          picker.value = "";
          status.textContent = `upload failed: ${err.message}`;
        }
        refreshCommandSoon();
      });
      wrap.append(label, picker, hidden, status);
    } else {
      const label = document.createElement("label");
      label.setAttribute("for", `opt_${spec.key}`);
      label.textContent = spec.label;
      let input;
      if (spec.type === "select") {
        input = document.createElement("select");
        for (const choice of spec.choices) {
          const opt = document.createElement("option");
          opt.value = typeof choice === "string" ? choice : choice.value;
          opt.textContent = typeof choice === "string" ? choice : choice.label;
          input.appendChild(opt);
        }
      } else if (spec.type === "textarea") {
        input = document.createElement("textarea");
        input.rows = spec.rows || 4;
        if (spec.placeholder) input.placeholder = spec.placeholder;
      } else {
        input = document.createElement("input");
        input.type = spec.type;
        if (spec.placeholder) input.placeholder = spec.placeholder;
        if (spec.min !== undefined) input.min = spec.min;
        if (spec.max !== undefined) input.max = spec.max;
        if (spec.step !== undefined) input.step = spec.step;
      }
      input.id = `opt_${spec.key}`;
      input.dataset.key = spec.key;
      if (spec.help) input.dataset.help = spec.help;
      if (spec.value !== undefined) input.value = spec.value;
      wrap.append(label, input);
    }
    els.optionsPanel.appendChild(wrap);
  }
  els.optionsPanel.querySelectorAll("input,select,textarea").forEach((node) => {
    node.addEventListener("input", refreshCommandSoon);
    node.addEventListener("change", refreshCommandSoon);
  });
}

function readOptions() {
  const options = {};
  els.optionsPanel.querySelectorAll("[data-key]").forEach((node) => {
    if (node.type === "checkbox") {
      options[node.dataset.key] = node.checked;
    } else {
      options[node.dataset.key] = node.value;
    }
  });
  return options;
}

function commandPayload() {
  const parts = actionParts();
  return {
    ...parts,
    model_dir: els.modelSelect.value,
    mesh_file: selectedMesh(),
    mesh_b: els.meshBSelect.value,
    options: readOptions()
  };
}

function refreshCommandSoon() {
  window.clearTimeout(app.commandTimer);
  app.commandTimer = window.setTimeout(refreshCommand, 120);
}

async function refreshCommand() {
  try {
    app.commandInfo = await api("/api/command", { method: "POST", body: commandPayload() });
    els.commandLine.textContent = app.commandInfo.display;
    els.flagList.innerHTML = "";
    for (const flag of app.commandInfo.flags) {
      const row = document.createElement("div");
      row.className = "flag-row";
      row.dataset.help = flag.reason || "Command argument";
      const code = document.createElement("code");
      code.textContent = flag.value === null ? flag.flag : `${flag.flag} ${flag.value}`;
      const text = document.createElement("span");
      text.textContent = flag.reason || "";
      row.append(code, text);
      els.flagList.appendChild(row);
    }
    setBadge("ready", "neutral");
    els.runBtn.disabled = false;
  } catch (err) {
    app.commandInfo = null;
    els.commandLine.textContent = err.message;
    els.flagList.innerHTML = "";
    setBadge("check inputs", "warn");
    els.runBtn.disabled = true;
  }
}

async function runCommand() {
  els.runBtn.disabled = true;
  els.cancelBtn.disabled = false;
  els.jobOutput.textContent = "";
  els.jobMeta.textContent = "starting";
  setBadge("running", "warn");
  app.lastAction = actionParts().action;
  try {
    const job = await api("/api/jobs", { method: "POST", body: commandPayload() });
    app.currentJob = job.id;
    pollJob();
  } catch (err) {
    els.jobOutput.textContent = `ERROR: ${err.message}`;
    els.jobMeta.textContent = "failed";
    setBadge("failed", "fail");
    els.runBtn.disabled = false;
    els.cancelBtn.disabled = true;
  }
}

async function pollJob() {
  if (!app.currentJob) return;
  try {
    const job = await api(`/api/jobs/${app.currentJob}`);
    els.jobOutput.textContent = job.output || "";
    els.jobOutput.scrollTop = els.jobOutput.scrollHeight;
    els.jobMeta.textContent = `${job.status}${job.return_code === null ? "" : ` (${job.return_code})`}`;
    const done = ["succeeded", "failed", "cancelled"].includes(job.status);
    if (done) {
      setBadge(job.status, job.status === "succeeded" ? "ok" : "fail");
      els.runBtn.disabled = false;
      els.cancelBtn.disabled = true;
      app.currentJob = null;
      await loadState(true);
      if (job.status === "succeeded" && app.lastAction === "generate") {
        const newest = [...app.data.meshes].sort((a, b) => b.modified - a.modified)[0];
        if (newest && newest.path !== selectedMesh()) {
          els.meshSearch.value = "";
          renderMeshes(false);
          els.meshSelect.value = newest.path;
          await loadSelectedMesh();
        }
      }
      return;
    }
    app.pollTimer = window.setTimeout(pollJob, 700);
  } catch (err) {
    els.jobMeta.textContent = err.message;
    els.runBtn.disabled = false;
    els.cancelBtn.disabled = true;
  }
}

async function cancelJob() {
  if (!app.currentJob) return;
  await api(`/api/jobs/${app.currentJob}/cancel`, { method: "POST", body: {} });
  els.cancelBtn.disabled = true;
}

function createViewer(canvas, statsEl) {
  try {
    return new MeshViewer(canvas, statsEl);
  } catch (err) {
    return new FallbackViewer(canvas, statsEl, err.message);
  }
}

function FallbackViewer(canvas, statsEl, reason) {
  this.statsEl = statsEl;
  this.reason = reason;
  let ctx = canvas.getContext("2d");
  if (!ctx && canvas.parentNode) {
    // A failed WebGL attempt can leave the canvas locked to a webgl context;
    // swap in a fresh canvas so 2D drawing works.
    const fresh = canvas.cloneNode(false);
    canvas.parentNode.replaceChild(fresh, canvas);
    canvas = fresh;
    ctx = canvas.getContext("2d");
  }
  this.canvas = canvas;
  this.ctx = ctx;
  new ResizeObserver(() => this.renderMessage(this.lastMessage || `Static preview mode: ${reason}`)).observe(canvas);
}

FallbackViewer.prototype.resize = function () {
  const rect = this.canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.floor(rect.width * dpr));
  const height = Math.max(1, Math.floor(rect.height * dpr));
  if (this.canvas.width !== width || this.canvas.height !== height) {
    this.canvas.width = width;
    this.canvas.height = height;
  }
  return { width, height, dpr };
};

FallbackViewer.prototype.renderMessage = function (message) {
  this.lastMessage = message;
  if (!this.ctx) {
    this.statsEl.textContent = message;
    return;
  }
  const { width, height, dpr } = this.resize();
  const ctx = this.ctx;
  ctx.fillStyle = "#181715";
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#f2eadc";
  ctx.font = `${14 * dpr}px Segoe UI, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const maxWidth = Math.max(220, width * 0.72);
  const words = message.split(" ");
  const lines = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width > maxWidth && line) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  const startY = height / 2 - ((lines.length - 1) * 20 * dpr) / 2;
  lines.forEach((text, index) => ctx.fillText(text, width / 2, startY + index * 20 * dpr));
};

FallbackViewer.prototype.clear = function (message) {
  this.statsEl.textContent = message;
  this.renderMessage(message);
};

FallbackViewer.prototype.load = async function (_url, label, mesh) {
  const preview = mesh && mesh.preview;
  if (!preview) {
    const message = `${label} selected. WebGL is unavailable and no PNG preview exists yet. Use Render PNG preview or Build model to create one.`;
    this.statsEl.textContent = message;
    this.renderMessage(message);
    return;
  }
  this.statsEl.textContent = `${label} | static PNG preview (WebGL unavailable: ${this.reason})`;
  await this.drawImage(`/api/file?path=${encodeURIComponent(preview)}&t=${Date.now()}`, label);
};

FallbackViewer.prototype.drawImage = function (url, label) {
  if (!this.ctx) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const { width, height } = this.resize();
      const ctx = this.ctx;
      ctx.fillStyle = "#181715";
      ctx.fillRect(0, 0, width, height);
      const scale = Math.min(width / image.width, height / image.height);
      const drawW = image.width * scale;
      const drawH = image.height * scale;
      ctx.drawImage(image, (width - drawW) / 2, (height - drawH) / 2, drawW, drawH);
      this.lastMessage = `${label} static preview`;
      resolve();
    };
    image.onerror = () => reject(new Error(`Could not load preview image for ${label}`));
    image.src = url;
  });
};

FallbackViewer.prototype.snap = function () {};

function openHelp() {
  els.helpScrim.hidden = false;
  els.helpDrawer.classList.add("open");
  els.helpDrawer.setAttribute("aria-hidden", "false");
}

function closeHelp() {
  els.helpDrawer.classList.remove("open");
  els.helpDrawer.setAttribute("aria-hidden", "true");
  window.setTimeout(() => {
    if (!els.helpDrawer.classList.contains("open")) {
      els.helpScrim.hidden = true;
    }
  }, 180);
}

function showHelpTip(target) {
  window.clearTimeout(app.helpTimer);
  const targetEl = target instanceof Element ? target : target?.parentElement;
  if (!targetEl) return;
  const helper = targetEl.closest("[data-help]");
  if (!helper || helper === els.helpTip) return;
  const text = helper.dataset.help;
  if (!text) return;
  app.helpTimer = window.setTimeout(() => {
    els.helpTip.textContent = text;
    els.helpTip.hidden = false;
    const rect = helper.getBoundingClientRect();
    const tipRect = els.helpTip.getBoundingClientRect();
    const margin = 10;
    let left = Math.min(window.innerWidth - tipRect.width - margin, Math.max(margin, rect.left));
    let top = rect.bottom + 8;
    if (top + tipRect.height + margin > window.innerHeight) {
      top = Math.max(margin, rect.top - tipRect.height - 8);
    }
    els.helpTip.style.left = `${left}px`;
    els.helpTip.style.top = `${top}px`;
  }, 1500);
}

function hideHelpTip() {
  window.clearTimeout(app.helpTimer);
  els.helpTip.hidden = true;
}

function wireUi() {
  els.helpBtn.addEventListener("click", openHelp);
  els.closeHelpBtn.addEventListener("click", closeHelp);
  els.helpScrim.addEventListener("click", closeHelp);
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeHelp();
  });
  document.addEventListener("mouseover", (event) => showHelpTip(event.target));
  document.addEventListener("focusin", (event) => showHelpTip(event.target));
  document.addEventListener("mouseout", (event) => {
    const targetEl = event.target instanceof Element ? event.target : event.target?.parentElement;
    if (!targetEl || !event.relatedTarget || !targetEl.closest("[data-help]")?.contains(event.relatedTarget)) {
      hideHelpTip();
    }
  });
  document.addEventListener("focusout", hideHelpTip);
  els.refreshBtn.addEventListener("click", () => loadState(true));
  els.copyCommandBtn.addEventListener("click", async () => {
    if (!app.commandInfo) return;
    await navigator.clipboard.writeText(app.commandInfo.display);
    setBadge("copied", "ok");
    window.setTimeout(() => setBadge("ready", "neutral"), 900);
  });
  els.meshSearch.addEventListener("input", () => {
    renderMeshes(true);
    loadSelectedMesh();
    refreshCommandSoon();
  });
  els.meshSelect.addEventListener("change", () => {
    loadSelectedMesh();
    refreshCommandSoon();
  });
  els.meshBSelect.addEventListener("change", refreshCommandSoon);
  els.modelSelect.addEventListener("change", refreshCommandSoon);
  els.actionSelect.addEventListener("change", () => {
    renderOptions();
    refreshCommandSoon();
  });
  els.runBtn.addEventListener("click", runCommand);
  els.cancelBtn.addEventListener("click", cancelJob);
  els.openExternalBtn.addEventListener("click", async () => {
    const path = selectedMesh();
    if (!path) return;
    try {
      await api("/api/open", { method: "POST", body: { path } });
      els.jobMeta.textContent = `opened ${path} in the system 3D app`;
    } catch (err) {
      els.jobMeta.textContent = `open failed: ${err.message}`;
    }
  });
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => viewer.snap(button.dataset.view));
  });
}

function v3sub(a, b) {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function v3cross(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0]
  ];
}

function v3norm(v) {
  const n = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / n, v[1] / n, v[2] / n];
}

function mat4Perspective(fovy, aspect, near, far) {
  const f = 1 / Math.tan(fovy / 2);
  const nf = 1 / (near - far);
  return new Float32Array([
    f / aspect, 0, 0, 0,
    0, f, 0, 0,
    0, 0, (far + near) * nf, -1,
    0, 0, 2 * far * near * nf, 0
  ]);
}

function mat4LookAt(eye, center, up) {
  const z = v3norm(v3sub(eye, center));
  const x = v3norm(v3cross(up, z));
  const y = v3cross(z, x);
  return new Float32Array([
    x[0], y[0], z[0], 0,
    x[1], y[1], z[1], 0,
    x[2], y[2], z[2], 0,
    -(x[0] * eye[0] + x[1] * eye[1] + x[2] * eye[2]),
    -(y[0] * eye[0] + y[1] * eye[1] + y[2] * eye[2]),
    -(z[0] * eye[0] + z[1] * eye[1] + z[2] * eye[2]),
    1
  ]);
}

function mat4Mul(a, b) {
  const out = new Float32Array(16);
  for (let c = 0; c < 4; c++) {
    for (let r = 0; r < 4; r++) {
      out[c * 4 + r] =
        a[0 * 4 + r] * b[c * 4 + 0] +
        a[1 * 4 + r] * b[c * 4 + 1] +
        a[2 * 4 + r] * b[c * 4 + 2] +
        a[3 * 4 + r] * b[c * 4 + 3];
    }
  }
  return out;
}

function compileShader(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(shader));
  }
  return shader;
}

function makeProgram(gl) {
  const vs = compileShader(gl, gl.VERTEX_SHADER, `
    attribute vec3 aPosition;
    attribute vec3 aNormal;
    uniform mat4 uMvp;
    varying float vLight;
    varying float vRim;
    void main() {
      vec3 n = normalize(aNormal);
      vec3 light = normalize(vec3(0.35, -0.65, 0.68));
      vLight = 0.30 + max(dot(n, light), 0.0) * 0.70;
      vRim = pow(1.0 - max(abs(n.z), 0.0), 2.0) * 0.15;
      gl_Position = uMvp * vec4(aPosition, 1.0);
    }
  `);
  const fs = compileShader(gl, gl.FRAGMENT_SHADER, `
    precision mediump float;
    uniform vec3 uColor;
    varying float vLight;
    varying float vRim;
    void main() {
      vec3 color = uColor * vLight + vec3(vRim);
      gl_FragColor = vec4(color, 1.0);
    }
  `);
  const program = gl.createProgram();
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(program));
  }
  return program;
}

function parseStl(buffer) {
  const dv = new DataView(buffer);
  const head = new TextDecoder().decode(buffer.slice(0, 512));
  const looksAscii = /^\s*solid/.test(head) && head.includes("facet");
  const declared = buffer.byteLength >= 84 ? dv.getUint32(80, true) : 0;
  const isBinary =
    buffer.byteLength >= 84 &&
    (84 + declared * 50 === buffer.byteLength ||
      (!looksAscii && declared > 0 && 84 + declared * 50 <= buffer.byteLength));
  if (!isBinary) {
    return parseAsciiStl(buffer);
  }
  const triCount = declared;
  const positions = new Float32Array(triCount * 9);
  const normals = new Float32Array(triCount * 9);
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  let offset = 84;
  let pi = 0;
  for (let i = 0; i < triCount; i++) {
    let n = [dv.getFloat32(offset, true), dv.getFloat32(offset + 4, true), dv.getFloat32(offset + 8, true)];
    offset += 12;
    const base = pi;
    for (let v = 0; v < 3; v++) {
      const x = dv.getFloat32(offset, true);
      const y = dv.getFloat32(offset + 4, true);
      const z = dv.getFloat32(offset + 8, true);
      positions[pi++] = x;
      positions[pi++] = y;
      positions[pi++] = z;
      min[0] = Math.min(min[0], x); min[1] = Math.min(min[1], y); min[2] = Math.min(min[2], z);
      max[0] = Math.max(max[0], x); max[1] = Math.max(max[1], y); max[2] = Math.max(max[2], z);
      offset += 12;
    }
    if (Math.hypot(n[0], n[1], n[2]) < 0.000001) {
      const a = [positions[base], positions[base + 1], positions[base + 2]];
      const b = [positions[base + 3], positions[base + 4], positions[base + 5]];
      const c = [positions[base + 6], positions[base + 7], positions[base + 8]];
      n = v3norm(v3cross(v3sub(b, a), v3sub(c, a)));
    } else {
      n = v3norm(n);
    }
    for (let k = 0; k < 9; k += 3) {
      normals[base + k] = n[0];
      normals[base + k + 1] = n[1];
      normals[base + k + 2] = n[2];
    }
    offset += 2;
  }
  return normalizeMesh({ positions, normals, min, max, triangles: triCount });
}

function parseAsciiStl(buffer) {
  const text = new TextDecoder().decode(buffer);
  const values = [];
  const re = /vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)/g;
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  let match;
  while ((match = re.exec(text))) {
    const x = Number(match[1]);
    const y = Number(match[2]);
    const z = Number(match[3]);
    values.push(x, y, z);
    min[0] = Math.min(min[0], x); min[1] = Math.min(min[1], y); min[2] = Math.min(min[2], z);
    max[0] = Math.max(max[0], x); max[1] = Math.max(max[1], y); max[2] = Math.max(max[2], z);
  }
  const positions = new Float32Array(values);
  const normals = new Float32Array(positions.length);
  for (let i = 0; i < positions.length; i += 9) {
    const a = [positions[i], positions[i + 1], positions[i + 2]];
    const b = [positions[i + 3], positions[i + 4], positions[i + 5]];
    const c = [positions[i + 6], positions[i + 7], positions[i + 8]];
    const n = v3norm(v3cross(v3sub(b, a), v3sub(c, a)));
    for (let k = 0; k < 9; k += 3) {
      normals[i + k] = n[0];
      normals[i + k + 1] = n[1];
      normals[i + k + 2] = n[2];
    }
  }
  return normalizeMesh({ positions, normals, min, max, triangles: positions.length / 9 });
}

function normalizeMesh(mesh) {
  const ext = [mesh.max[0] - mesh.min[0], mesh.max[1] - mesh.min[1], mesh.max[2] - mesh.min[2]];
  const center = [(mesh.min[0] + mesh.max[0]) / 2, (mesh.min[1] + mesh.max[1]) / 2, (mesh.min[2] + mesh.max[2]) / 2];
  const scale = 2 / (Math.max(ext[0], ext[1], ext[2]) || 1);
  const out = new Float32Array(mesh.positions.length);
  for (let i = 0; i < mesh.positions.length; i += 3) {
    out[i] = (mesh.positions[i] - center[0]) * scale;
    out[i + 1] = (mesh.positions[i + 1] - center[1]) * scale;
    out[i + 2] = (mesh.positions[i + 2] - center[2]) * scale;
  }
  return { positions: out, normals: mesh.normals, min: mesh.min, max: mesh.max, extents: ext, triangles: mesh.triangles };
}

function MeshViewer(canvas, statsEl) {
  this.canvas = canvas;
  this.statsEl = statsEl;
  this.gl = (
    canvas.getContext("webgl2", { antialias: true }) ||
    canvas.getContext("webgl", { antialias: true }) ||
    canvas.getContext("experimental-webgl", { antialias: true })
  );
  this.mesh = null;
  this.yaw = Math.PI / 4;
  this.pitch = 0.42;
  this.distance = 4.4;
  this.dragging = false;
  if (!this.gl) {
    throw new Error("WebGL is not available in this browser");
  }
  this.program = makeProgram(this.gl);
  this.locations = {
    pos: this.gl.getAttribLocation(this.program, "aPosition"),
    normal: this.gl.getAttribLocation(this.program, "aNormal"),
    mvp: this.gl.getUniformLocation(this.program, "uMvp"),
    color: this.gl.getUniformLocation(this.program, "uColor")
  };
  this.posBuffer = this.gl.createBuffer();
  this.normalBuffer = this.gl.createBuffer();
  this.bindEvents();
  new ResizeObserver(() => this.render()).observe(canvas);
}

MeshViewer.prototype.clear = function (message) {
  this.mesh = null;
  this.statsEl.textContent = message;
  this.render();
};

MeshViewer.prototype.load = async function (url, label) {
  this.statsEl.textContent = `Loading ${label}`;
  const res = await fetch(url);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      if (err.error) detail = err.error;
    } catch (ignored) {}
    this.clear(`Could not load ${label}: ${detail}`);
    throw new Error(detail);
  }
  const buffer = await res.arrayBuffer();
  const mesh = parseStl(buffer);
  if (!mesh.triangles) {
    this.clear(`${label} contains no triangles (not a valid STL?)`);
    return;
  }
  this.mesh = mesh;
  const gl = this.gl;
  gl.bindBuffer(gl.ARRAY_BUFFER, this.posBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, mesh.positions, gl.STATIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, this.normalBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, mesh.normals, gl.STATIC_DRAW);
  this.statsEl.textContent =
    `${label} | ${mesh.extents.map((v) => v.toFixed(2)).join(" x ")} mm | ${Math.round(mesh.triangles).toLocaleString()} tris`;
  this.render();
};

MeshViewer.prototype.snap = function (view) {
  const views = {
    iso: [Math.PI / 4, 0.42],
    front: [0, 0],
    right: [Math.PI / 2, 0],
    top: [0, Math.PI / 2 - 0.001]
  };
  const next = views[view] || views.iso;
  this.yaw = next[0];
  this.pitch = next[1];
  this.render();
};

MeshViewer.prototype.bindEvents = function () {
  let lastX = 0;
  let lastY = 0;
  this.canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  this.canvas.addEventListener("mousedown", (event) => {
    if (event.button !== 1 && event.button !== 0) return;
    event.preventDefault();
    this.dragging = true;
    this.canvas.classList.add("dragging");
    lastX = event.clientX;
    lastY = event.clientY;
  });
  window.addEventListener("mouseup", () => {
    this.dragging = false;
    this.canvas.classList.remove("dragging");
  });
  window.addEventListener("mousemove", (event) => {
    if (!this.dragging) return;
    const dx = event.clientX - lastX;
    const dy = event.clientY - lastY;
    lastX = event.clientX;
    lastY = event.clientY;
    this.yaw += dx * 0.01;
    this.pitch = Math.max(-1.45, Math.min(1.45, this.pitch + dy * 0.01));
    this.render();
  });
  this.canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    this.distance = Math.max(2.2, Math.min(10, this.distance * (event.deltaY > 0 ? 1.08 : 0.92)));
    this.render();
  }, { passive: false });
};

MeshViewer.prototype.render = function () {
  const gl = this.gl;
  if (!gl) {
    this.statsEl.textContent = "WebGL is not available";
    return;
  }
  const rect = this.canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.floor(rect.width * dpr));
  const height = Math.max(1, Math.floor(rect.height * dpr));
  if (this.canvas.width !== width || this.canvas.height !== height) {
    this.canvas.width = width;
    this.canvas.height = height;
  }
  gl.viewport(0, 0, width, height);
  gl.clearColor(0.094, 0.090, 0.082, 1);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  if (!this.mesh) return;

  const cp = Math.cos(this.pitch);
  const eye = [
    Math.sin(this.yaw) * cp * this.distance,
    -Math.cos(this.yaw) * cp * this.distance,
    Math.sin(this.pitch) * this.distance
  ];
  const proj = mat4Perspective(45 * Math.PI / 180, width / height, 0.05, 50);
  const view = mat4LookAt(eye, [0, 0, 0], [0, 0, 1]);
  const mvp = mat4Mul(proj, view);

  gl.enable(gl.DEPTH_TEST);
  gl.useProgram(this.program);
  gl.uniformMatrix4fv(this.locations.mvp, false, mvp);
  gl.uniform3f(this.locations.color, 0.76, 0.67, 0.52);

  gl.bindBuffer(gl.ARRAY_BUFFER, this.posBuffer);
  gl.enableVertexAttribArray(this.locations.pos);
  gl.vertexAttribPointer(this.locations.pos, 3, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ARRAY_BUFFER, this.normalBuffer);
  gl.enableVertexAttribArray(this.locations.normal);
  gl.vertexAttribPointer(this.locations.normal, 3, gl.FLOAT, false, 0, 0);
  gl.drawArrays(gl.TRIANGLES, 0, this.mesh.positions.length / 3);
};

viewer = createViewer(els.canvas, els.viewerStats);
wireUi();
loadState(false).catch((err) => {
  els.jobOutput.textContent = `ERROR: ${err.message}`;
  setBadge("server error", "fail");
});
