from pathlib import Path
import subprocess
import sys
from typing import List, Dict, Any
import os
import json
from datetime import datetime

import yaml
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"
DEFAULT_METASPEC = BASE_DIR / "metaspec.yaml"
RUNS_DIR = BASE_DIR / "runs"
RUNS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Code Agent Control Panel")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def _safe_load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    return yaml.safe_load(text) or {}


def load_config() -> Dict[str, Any]:
    cfg = _safe_load_yaml(CONFIG_PATH)
    if not cfg:
        cfg = {
            "provider": {"name": "ollama", "model": "deepseek-coder:latest"},
            "timeouts": {"llm": 600, "process": 900},
            "autofix": {"max_iterations": 2},
            "project_root": "./outputs",
        }

    cfg.setdefault("provider", {})
    cfg["provider"].setdefault("name", "ollama")
    cfg["provider"].setdefault("model", "deepseek-coder:latest")

    cfg.setdefault("timeouts", {})
    cfg["timeouts"].setdefault("llm", 600)
    cfg["timeouts"].setdefault("process", 900)

    cfg.setdefault("autofix", {})
    cfg["autofix"].setdefault("max_iterations", 0)

    cfg.setdefault("project_root", "./outputs")

    return cfg


def load_metaspec(path: Path) -> Dict[str, Any]:
    spec = _safe_load_yaml(path)
    spec.setdefault("project", {})
    spec["project"].setdefault("name", "")
    spec["project"].setdefault("summary", "")
    return spec


def available_metaspecs() -> List[Path]:
    candidates: List[Path] = []

    # root metaspecs
    for name in ("metaspec.yaml", "metaspec.yml"):
        p = BASE_DIR / name
        if p.exists():
            candidates.append(p)

    # metaspecs/ directory
    spec_dir = BASE_DIR / "metaspecs"
    if spec_dir.exists() and spec_dir.is_dir():
        for pattern in ("*.yaml", "*.yml"):
            for p in spec_dir.glob(pattern):
                candidates.append(p)

    seen = set()
    unique: List[Path] = []
    for p in candidates:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        unique.append(p)
    return unique


def _read_log_tail(path: Path, max_bytes: int = 8000) -> str:
    if not path.exists():
        return ""
    data = path.read_bytes()
    if len(data) <= max_bytes:
        return data.decode("utf-8", errors="ignore")
    return data[-max_bytes:].decode("utf-8", errors="ignore")


def _process_status(pid: int) -> str:
    if not pid:
        return "unknown"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "finished"
    except PermissionError:
        return "running"
    else:
        return "running"


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    cfg = load_config()

    specs = available_metaspecs()
    if not specs:
        specs = [DEFAULT_METASPEC]

    current_spec = DEFAULT_METASPEC if DEFAULT_METASPEC.exists() else specs[0]
    spec = load_metaspec(current_spec)

    metaspec_options = []
    for p in specs:
        metaspec_options.append(
            {
                "value": str(p.relative_to(BASE_DIR)),
                "label": p.name,
                "selected": p.resolve() == current_spec.resolve(),
            }
        )

    project_name = spec.get("project", {}).get("name", "")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "cfg": cfg,
            "metaspec_options": metaspec_options,
            "project_name": project_name,
        },
    )


@app.post("/run", response_class=HTMLResponse)
async def run_agent(
    request: Request,
    provider_name: str = Form(...),
    provider_model: str = Form(...),
    timeout_llm: int = Form(...),
    timeout_process: int = Form(...),
    autofix_max_iterations: int = Form(...),
    project_root: str = Form(...),
    metaspec_path: str = Form(...),
    project_name: str = Form(""),
):
    cfg = load_config()
    cfg["provider"]["name"] = provider_name.strip()
    cfg["provider"]["model"] = provider_model.strip()
    cfg["timeouts"]["llm"] = int(timeout_llm)
    cfg["timeouts"]["process"] = int(timeout_process)
    cfg["autofix"]["max_iterations"] = int(autofix_max_iterations)
    cfg["project_root"] = project_root.strip() or cfg["project_root"]

    # Save back to config.yaml for next runs
    CONFIG_PATH.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    # Prepare metaspec.yaml used by agent.py
    selected_source = (BASE_DIR / metaspec_path).resolve()
    spec = load_metaspec(selected_source)
    override_name = project_name.strip()
    if override_name:
        spec.setdefault("project", {})
        spec["project"]["name"] = override_name

    DEFAULT_METASPEC.write_text(
        yaml.safe_dump(spec, sort_keys=False), encoding="utf-8"
    )

    effective_name = spec.get("project", {}).get("name", "")
    proj_dir = Path(cfg["project_root"]).joinpath(effective_name)

    # Create run id and log/meta files
    run_id = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    log_path = RUNS_DIR / f"{run_id}.log"
    meta_path = RUNS_DIR / f"{run_id}.json"

    log_file = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "agent.py"],
        cwd=str(BASE_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log_file.close()

    meta = {
        "run_id": run_id,
        "pid": proc.pid,
        "project_dir": str(proj_dir),
        "metaspec_path": str(DEFAULT_METASPEC),
        "config": cfg,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_status(request: Request, run_id: str):
    log_path = RUNS_DIR / f"{run_id}.log"
    meta_path = RUNS_DIR / f"{run_id}.json"

    if not log_path.exists() or not meta_path.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    pid = meta.get("pid", 0)
    status = _process_status(pid)
    log_tail = _read_log_tail(log_path)

    return templates.TemplateResponse(
        "run_progress.html",
        {
            "request": request,
            "run_id": run_id,
            "status": status,
            "log_tail": log_tail,
            "project_dir": meta.get("project_dir", ""),
        },
    )
