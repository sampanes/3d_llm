"""
Local web GUI for this repo's model and mesh command-line tools.

The server is intentionally thin: it lists local model/mesh files, builds
whitelisted commands, runs them as background jobs, and serves static UI files.
All modeling and mesh work stays in the existing scripts.

Usage:
    .venv\\Scripts\\python -m scripts.gui_server
    .venv\\Scripts\\python -m scripts.gui_server --port 8765
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "gui_static"
PYTHON_DISPLAY = r".venv\Scripts\python"
MESH_ROOTS = ("experiments", "gcode_examples", "models", "output", "stl_library")
TEXT_SUFFIXES = {".json", ".md", ".txt", ".log"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
FILE_SUFFIXES = {".stl", ".obj", ".ply", ".glb", ".3mf", *IMAGE_SUFFIXES, *TEXT_SUFFIXES}
GENERATE_PROVIDERS = ("anthropic", "openai", "google", "ollama")
GENERATE_PIPELINES = ("openscad", "cadquery", "sdf")
UPLOAD_DIR = ROOT / "output" / "uploads"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _provider_status() -> dict:
    """True per provider when its API key is configured (ollama is keyless)."""
    return {
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "google": bool(os.environ.get("GOOGLE_API_KEY")),
        "ollama": True,
    }


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _safe_path(raw: str) -> Path:
    if not raw:
        raise ValueError("path is required")
    path = (ROOT / raw).resolve()
    if not _is_relative_to(path, ROOT):
        raise ValueError("path must stay inside the project")
    return path


def _rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def _display_command(command: list[str]) -> str:
    shown = command[:]
    try:
        if Path(command[0]).resolve() == Path(sys.executable).resolve():
            shown[0] = PYTHON_DISPLAY
    except OSError:
        pass
    return subprocess.list2cmdline(shown)


def _add_flag(
    command: list[str],
    flags: list[dict],
    flag: str,
    value: object | None = None,
    *,
    enabled: bool = True,
    reason: str = "",
) -> None:
    if not enabled:
        return
    if value is None or value is True:
        command.append(flag)
        flags.append({"flag": flag, "value": None, "reason": reason})
        return
    command.extend([flag, str(value)])
    flags.append({"flag": flag, "value": str(value), "reason": reason})


def _positive_int(value: object, default: int, minimum: int = 1, maximum: int = 999999) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        num = default
    return max(minimum, min(maximum, num))


def _positive_float(
    value: object,
    default: float,
    minimum: float = 0.0001,
    maximum: float = 999999.0,
) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = default
    return max(minimum, min(maximum, num))


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"expected a number, got {value!r}")


def _output_path(raw: object) -> str | None:
    if raw in (None, ""):
        return None
    return _rel(_safe_path(str(raw)))


def _module_command(module: str) -> list[str]:
    return [sys.executable, "-m", module]


def _build_command(payload: dict) -> dict:
    action = str(payload.get("action") or "")
    options = payload.get("options") or {}
    flags: list[dict] = []

    if action == "generate":
        prompt = str(options.get("prompt") or payload.get("prompt") or "").strip()
        if len(prompt) < 4:
            raise ValueError("prompt is required - describe the model to generate")
        provider = str(options.get("llm") or "anthropic")
        if provider not in GENERATE_PROVIDERS:
            raise ValueError("unsupported LLM provider")
        pipeline = str(options.get("pipeline") or "openscad")
        if pipeline not in GENERATE_PIPELINES:
            raise ValueError("unsupported pipeline")
        command = _module_command("scripts.generate")
        command.extend(["-p", prompt])
        flags.append({"flag": "-p", "value": prompt, "reason": "model description sent to the LLM"})
        _add_flag(command, flags, "--llm", provider, reason="LLM provider")
        model = str(options.get("model") or "").strip()
        _add_flag(command, flags, "--model", model, enabled=bool(model), reason="exact model id override")
        _add_flag(command, flags, "--pipeline", pipeline, reason="code target (sdf = organic shapes)")
        _add_flag(
            command,
            flags,
            "--few-shot",
            enabled=bool(options.get("few_shot")),
            reason="include worked examples in the prompt",
        )
        _add_flag(
            command,
            flags,
            "--temperature",
            _positive_float(options.get("temperature"), 0.7, 0.0, 2.0),
            reason="LLM sampling temperature",
        )
        _add_flag(
            command,
            flags,
            "--max-tokens",
            _positive_int(options.get("max_tokens"), 8192, 256, 64000),
            reason="LLM response token budget",
        )
        _add_flag(
            command,
            flags,
            "--skip-validation",
            enabled=bool(options.get("skip_validation")),
            reason="do not validate the generated STL",
        )
        image = str(options.get("image") or "").strip()
        if image:
            img_path = _safe_path(image)
            if not img_path.is_file() or img_path.suffix.lower() not in IMAGE_SUFFIXES:
                raise ValueError("reference image not found or not an image file")
            _add_flag(
                command,
                flags,
                "--image",
                _rel(img_path),
                reason="reference image the LLM sees alongside the prompt",
            )
    elif action == "build_model":
        model_dir = _rel(_safe_path(str(payload.get("model_dir") or "")))
        command = _module_command("scripts.build_model")
        command.append(model_dir)
        flags.append({"flag": "MODEL_DIR", "value": model_dir, "reason": "model folder"})
        _add_flag(
            command,
            flags,
            "--skip-preview",
            enabled=bool(options.get("skip_preview")),
            reason="do not render PNG previews",
        )
        _add_flag(
            command,
            flags,
            "--skip-validation",
            enabled=bool(options.get("skip_validation")),
            reason="do not validate generated STLs",
        )
        _add_flag(
            command,
            flags,
            "--timeout",
            _positive_int(options.get("timeout"), 900, 30, 86400),
            reason="model.py timeout in seconds",
        )
    elif action == "validate":
        mesh = _rel(_safe_path(str(payload.get("mesh_file") or "")))
        command = _module_command("scripts.validate_stl")
        command.append(mesh)
        flags.append({"flag": "MESH_FILE", "value": mesh, "reason": "mesh to inspect"})
        _add_flag(command, flags, "--json", enabled=bool(options.get("json")), reason="machine-readable report")
        _add_flag(command, flags, "--fix", enabled=bool(options.get("fix")), reason="attempt light repair")
        out = _output_path(options.get("output"))
        _add_flag(command, flags, "-o", out, enabled=bool(out), reason="repaired STL output")
    elif action == "mesh_preview":
        mesh = _rel(_safe_path(str(payload.get("mesh_file") or "")))
        views = str(options.get("views") or "iso,front,right,top")
        command = _module_command("scripts.mesh_preview")
        command.append(mesh)
        flags.append({"flag": "MESH_FILE", "value": mesh, "reason": "mesh to render"})
        out = _output_path(options.get("output"))
        _add_flag(command, flags, "-o", out, enabled=bool(out), reason="PNG output")
        _add_flag(command, flags, "--views", views, reason="view panels")
        _add_flag(command, flags, "--size", _positive_int(options.get("size"), 640, 160, 2048), reason="pixels per view")
        color = str(options.get("color") or "#cfc4a7")
        _add_flag(command, flags, "--color", color, reason="mesh material color")
        _add_flag(command, flags, "--separate", enabled=bool(options.get("separate")), reason="one file per view")
        _add_flag(command, flags, "--no-grid", enabled=bool(options.get("no_grid")), reason="hide dimension grid")
    elif action == "edit":
        op = str(payload.get("operation") or "")
        if op not in {
            "repair",
            "remesh",
            "place",
            "scale",
            "rotate",
            "translate",
            "hollow",
            "boolean",
            "cut",
            "decimate",
            "smooth",
            "convert",
        }:
            raise ValueError("unsupported edit operation")
        mesh = _rel(_safe_path(str(payload.get("mesh_file") or "")))
        command = _module_command("scripts.edit_stl")
        command.append(op)
        flags.append({"flag": "OP", "value": op, "reason": "edit_stl subcommand"})

        if op == "boolean":
            bool_op = str(options.get("boolean_op") or "union")
            if bool_op not in {"union", "difference", "intersection"}:
                raise ValueError("unsupported boolean operation")
            other = _rel(_safe_path(str(payload.get("mesh_b") or "")))
            command.extend([bool_op, mesh, other])
            flags.append({"flag": "BOOLEAN_OP", "value": bool_op, "reason": "mesh boolean operation"})
            flags.append({"flag": "MESH_A", "value": mesh, "reason": "left-hand mesh"})
            flags.append({"flag": "MESH_B", "value": other, "reason": "right-hand mesh"})
        else:
            command.append(mesh)
            flags.append({"flag": "MESH_FILE", "value": mesh, "reason": "mesh to edit"})

        if op == "repair":
            _add_flag(command, flags, "--force-remesh", enabled=bool(options.get("force_remesh")), reason="skip light fixes")
            voxel = _optional_float(options.get("voxel"))
            _add_flag(command, flags, "--voxel", voxel, enabled=voxel is not None, reason="remesh voxel size in mm")
        elif op == "remesh":
            voxel = _optional_float(options.get("voxel"))
            _add_flag(command, flags, "--voxel", voxel, enabled=voxel is not None, reason="voxel size in mm")
        elif op == "place":
            _add_flag(command, flags, "--no-center", enabled=bool(options.get("no_center")), reason="only drop to Z=0")
        elif op == "scale":
            factor = _optional_float(options.get("factor"))
            to_x = _optional_float(options.get("to_x"))
            to_y = _optional_float(options.get("to_y"))
            to_z = _optional_float(options.get("to_z"))
            _add_flag(command, flags, "--factor", factor, enabled=factor is not None, reason="uniform scale factor")
            _add_flag(command, flags, "--to-x", to_x, enabled=to_x is not None, reason="target X size")
            _add_flag(command, flags, "--to-y", to_y, enabled=to_y is not None, reason="target Y size")
            _add_flag(command, flags, "--to-z", to_z, enabled=to_z is not None, reason="target Z size")
            _add_flag(command, flags, "--stretch", enabled=bool(options.get("stretch")), reason="allow non-uniform scaling")
        elif op == "rotate":
            axis = str(options.get("axis") or "z")
            if axis not in {"x", "y", "z"}:
                raise ValueError("axis must be x, y, or z")
            _add_flag(command, flags, "--axis", axis, reason="rotation axis")
            _add_flag(command, flags, "--angle", _positive_float(options.get("angle"), 90.0, -3600, 3600), reason="degrees")
        elif op == "translate":
            _add_flag(command, flags, "--x", _optional_float(options.get("x")) or 0.0, reason="X offset")
            _add_flag(command, flags, "--y", _optional_float(options.get("y")) or 0.0, reason="Y offset")
            _add_flag(command, flags, "--z", _optional_float(options.get("z")) or 0.0, reason="Z offset")
        elif op == "hollow":
            _add_flag(command, flags, "--wall", _positive_float(options.get("wall"), 2.0), reason="wall thickness in mm")
            voxel = _optional_float(options.get("voxel"))
            _add_flag(command, flags, "--voxel", voxel, enabled=voxel is not None, reason="voxel size in mm")
        elif op == "cut":
            axis = str(options.get("cut_axis") or "z")
            if axis not in {"x", "y", "z"}:
                raise ValueError("cut axis must be x, y, or z")
            value = _optional_float(options.get("cut_value"))
            if value is None:
                value = 0.0
            keep = str(options.get("keep") or "below")
            if keep not in {"above", "below"}:
                raise ValueError("keep must be above or below")
            _add_flag(command, flags, f"--{axis}", value, reason="cut plane position")
            _add_flag(command, flags, "--keep", keep, reason="side of the plane to keep")
            _add_flag(command, flags, "--no-cap", enabled=bool(options.get("no_cap")), reason="leave cut face open")
        elif op == "decimate":
            faces = options.get("faces")
            ratio = options.get("ratio")
            if faces not in (None, ""):
                _add_flag(command, flags, "--faces", _positive_int(faces, 1000, 4), reason="target triangle count")
            else:
                _add_flag(command, flags, "--ratio", _positive_float(ratio, 0.5, 0.01, 1.0), reason="fraction of faces to keep")
        elif op == "smooth":
            _add_flag(command, flags, "--iterations", _positive_int(options.get("iterations"), 10, 1, 500), reason="Taubin passes")
        elif op == "convert":
            out = _output_path(options.get("output"))
            if not out:
                raise ValueError("convert requires an output path")
            _add_flag(command, flags, "-o", out, reason="converted mesh output")

        if op not in {"convert"}:
            out = _output_path(options.get("output"))
            _add_flag(command, flags, "-o", out, enabled=bool(out), reason="output mesh path")
    else:
        raise ValueError("unsupported action")

    return {
        "action": action,
        "command": command,
        "display": _display_command(command),
        "flags": flags,
    }


def _list_models() -> list[dict]:
    models_dir = ROOT / "models"
    items = []
    if not models_dir.is_dir():
        return items
    for path in sorted(models_dir.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        model_py = path / "model.py"
        if not model_py.is_file():
            continue
        output = path / "output"
        stls = sorted(_rel(p) for p in output.glob("*.stl")) if output.is_dir() else []
        items.append(
            {
                "name": path.name,
                "path": _rel(path),
                "spec": _rel(path / "spec.md") if (path / "spec.md").is_file() else None,
                "params": _rel(path / "params.json") if (path / "params.json").is_file() else None,
                "stls": stls,
            }
        )
    return items


def _list_meshes() -> list[dict]:
    files: list[Path] = []
    for root_name in MESH_ROOTS:
        root = ROOT / root_name
        if root.is_dir():
            files.extend(p for p in root.rglob("*.stl") if p.is_file())
    items = []
    seen = set()
    for path in sorted(files):
        if "tools" in path.parts:
            continue
        rel = _rel(path)
        if rel in seen:
            continue
        seen.add(rel)
        stat = path.stat()
        preview = path.with_name(path.stem + "_preview.png")
        items.append(
            {
                "path": rel,
                "name": path.name,
                "directory": _rel(path.parent),
                "size_bytes": stat.st_size,
                "modified": int(stat.st_mtime),
                "preview": _rel(preview) if preview.is_file() else None,
            }
        )
    return items


def _state() -> dict:
    return {
        "root": str(ROOT),
        "models": _list_models(),
        "meshes": _list_meshes(),
        "python": PYTHON_DISPLAY,
        "providers": _provider_status(),
    }


@dataclass
class Job:
    id: str
    command_info: dict
    status: str = "queued"
    output: list[str] = field(default_factory=list)
    return_code: int | None = None
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    error: str | None = None
    process: subprocess.Popen | None = None

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "return_code": self.return_code,
            "display": self.command_info["display"],
            "flags": self.command_info["flags"],
            "output": "".join(self.output),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error": self.error,
        }


JOBS: dict[str, Job] = {}
JOBS_LOCK = threading.Lock()

# Host header allowlist (DNS-rebinding guard). When the server is bound to a
# loopback address this is the set of acceptable Host names; main() sets it to
# None when bound to a non-loopback address, where the operator has explicitly
# opted into exposure and Host checking would just get in the way.
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
ALLOWED_HOSTS: set[str] | None = set(LOOPBACK_HOSTS)


def _hostname_only(host_header: str) -> str:
    """Strip an optional :port from a Host header, keeping IPv6 literals intact."""
    host = (host_header or "").strip()
    if host.startswith("["):  # [::1]:8765  ->  ::1
        return host[1:].split("]", 1)[0]
    if ":" in host:  # 127.0.0.1:8765  ->  127.0.0.1
        return host.rsplit(":", 1)[0]
    return host


def _run_job(job: Job) -> None:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    creationflags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW
    try:
        job.status = "running"
        proc = subprocess.Popen(
            job.command_info["command"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            creationflags=creationflags,
        )
        job.process = proc
        if proc.stdout is None:
            raise RuntimeError("subprocess stdout pipe was not created")
        for line in proc.stdout:
            with JOBS_LOCK:
                job.output.append(line)
        job.return_code = proc.wait()
        job.status = "succeeded" if job.return_code == 0 else "failed"
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.output.append(f"ERROR: {exc}\n")
    finally:
        job.ended_at = time.time()
        job.process = None


def _start_job(payload: dict) -> Job:
    command_info = _build_command(payload)
    job = Job(id=uuid.uuid4().hex[:12], command_info=command_info)
    with JOBS_LOCK:
        JOBS[job.id] = job
    thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
    thread.start()
    return job


class GuiHandler(BaseHTTPRequestHandler):
    server_version = "ModelGui/0.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stdout.write(f"[gui] {self.address_string()} - {fmt % args}\n")

    def _send_json(self, payload: object, status: int = 200) -> None:
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, message: str, status: int = 400) -> None:
        self._send_json({"error": message}, status=status)

    def _host_allowed(self) -> bool:
        """Reject requests whose Host header isn't an expected loopback name.

        This blocks DNS-rebinding attacks: a malicious web page that resolves
        its own domain to 127.0.0.1 can reach this port, but the browser sends
        Host: evil.example, which is not in the allowlist. Disabled (returns
        True) when the server is intentionally bound to a non-loopback address.
        """
        if ALLOWED_HOSTS is None:
            return True
        return _hostname_only(self.headers.get("Host", "")) in ALLOWED_HOSTS

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def _serve_static(self, route: str) -> None:
        if route == "/":
            path = STATIC_DIR / "index.html"
        else:
            path = (STATIC_DIR / unquote(route.removeprefix("/static/"))).resolve()
            if not _is_relative_to(path, STATIC_DIR):
                self.send_error(403)
                return
        if not path.is_file():
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_file(self, query: dict) -> None:
        raw = (query.get("path") or [""])[0]
        try:
            path = _safe_path(raw)
        except ValueError as exc:
            self._send_error(str(exc), 400)
            return
        if not path.is_file() or path.suffix.lower() not in FILE_SUFFIXES:
            self._send_error("file not found or unsupported", 404)
            return
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if not self._host_allowed():
            self._send_error("forbidden: unexpected Host header", 403)
            return
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)
        if route == "/" or route.startswith("/static/"):
            self._serve_static(route)
            return
        if route == "/api/state":
            self._send_json(_state())
            return
        if route == "/api/file":
            self._serve_file(query)
            return
        if route.startswith("/api/jobs/"):
            job_id = route.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                snap = job.snapshot() if job else None
            if snap is None:
                self._send_error("job not found", 404)
            else:
                self._send_json(snap)
            return
        self.send_error(404)

    def _handle_upload(self, payload: dict) -> None:
        """Save a base64-encoded reference image into output/uploads/."""
        import base64
        import re

        name = str(payload.get("filename") or "image.png")
        suffix = Path(name).suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            raise ValueError(
                f"unsupported image type '{suffix}' (use {', '.join(sorted(IMAGE_SUFFIXES))})"
            )
        data = str(payload.get("data") or "")
        # Accept both bare base64 and data-URL form
        if data.startswith("data:"):
            data = data.split(",", 1)[-1]
        try:
            raw = base64.b64decode(data, validate=True)
        except Exception:
            raise ValueError("image data is not valid base64")
        if not raw:
            raise ValueError("image data is empty")
        if len(raw) > MAX_UPLOAD_BYTES:
            raise ValueError(f"image too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)")

        stem = re.sub(r"[^\w-]+", "_", Path(name).stem).strip("_") or "image"
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        path = UPLOAD_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_{stem[:40]}{suffix}"
        path.write_bytes(raw)
        self._send_json({"ok": True, "path": _rel(path), "size_bytes": len(raw)})

    def do_POST(self) -> None:
        if not self._host_allowed():
            self._send_error("forbidden: unexpected Host header", 403)
            return
        parsed = urlparse(self.path)
        route = parsed.path
        try:
            payload = self._read_json()
            if route == "/api/command":
                self._send_json(_build_command(payload))
                return
            if route == "/api/jobs":
                job = _start_job(payload)
                self._send_json(job.snapshot(), status=202)
                return
            if route == "/api/upload":
                self._handle_upload(payload)
                return
            if route == "/api/open":
                path = _safe_path(str(payload.get("path") or ""))
                if not path.is_file() or path.suffix.lower() not in FILE_SUFFIXES:
                    self._send_error("file not found or unsupported", 404)
                    return
                if not hasattr(os, "startfile"):
                    self._send_error("open in external app is Windows-only", 501)
                    return
                os.startfile(str(path))
                self._send_json({"ok": True, "path": _rel(path)})
                return
            if route.startswith("/api/jobs/") and route.endswith("/cancel"):
                job_id = route.split("/")[-2]
                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                if not job:
                    self._send_error("job not found", 404)
                    return
                if job.process and job.status == "running":
                    job.process.terminate()
                    job.status = "cancelled"
                    job.ended_at = time.time()
                self._send_json(job.snapshot())
                return
            self.send_error(404)
        except ValueError as exc:
            self._send_error(str(exc), 400)
        except json.JSONDecodeError:
            self._send_error("invalid JSON", 400)
        except Exception as exc:
            self._send_error(str(exc), 500)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local 3D model GUI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args(argv)

    global ALLOWED_HOSTS
    if args.host in LOOPBACK_HOSTS or args.host == "":
        ALLOWED_HOSTS = set(LOOPBACK_HOSTS)
    else:
        # Operator explicitly bound to a reachable address: disable the Host
        # guard, but make the exposure loud. This server has NO authentication
        # and can run local scripts and spend API credits.
        ALLOWED_HOSTS = None
        print(
            "WARNING: binding to a non-loopback address. This server has no "
            "authentication and can run local scripts and spend API credits - "
            "anyone who can reach this port can drive it. Use only on a network "
            "you trust."
        )

    server = ThreadingHTTPServer((args.host, args.port), GuiHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"3D LLM GUI serving {ROOT}")
    print(f"Open {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
