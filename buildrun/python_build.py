import subprocess, sys, os
from pathlib import Path
from rich import print as rprint  # add at top

def build_and_test(spec, proj_dir:Path, cfg):
    report = {"success": False, "stages":[]}
    def stage(name, run):
        rprint(f"[blue]Stage:[/blue] {name}")   # ← add this
        try:
            run()
            report["stages"].append({"stage":name,"status":"ok","notes":""})
        except subprocess.CalledProcessError as e:
            out = (e.stdout or b"").decode(errors="ignore") + (e.stderr or b"").decode(errors="ignore")
            report["stages"].append({"stage":name,"status":"fail","notes":out[-2000:]})
            raise
        except Exception as e:
            report["stages"].append({"stage":name,"status":"fail","notes":str(e)})
            raise
    try:
        # local venv inside project
        stage("venv", lambda: _run(["python","-m","venv",".venv"], proj_dir))
        pip = proj_dir/".venv/bin/pip"
        py  = proj_dir/".venv/bin/python"
        if (proj_dir/"requirements.txt").exists():
            stage("pip-up", lambda: _run([str(py), "-m", "pip", "install", "--upgrade", "pip"], proj_dir))
            stage("install", lambda: _run([str(pip), "install", "-r", "requirements.txt"], proj_dir))
        test_cmd = spec["build"]["commands"].get("test","pytest -q")
        stage("test", lambda: _run(test_cmd, proj_dir, shell=True, env=_env_with_path(proj_dir)))
        report["success"] = True
    except Exception:
        report["success"] = False
    return report["success"], report

def _env_with_path(proj_dir:Path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(proj_dir/"src")
    return env

def _run(cmd, cwd:Path, shell=False, env=None):
    if isinstance(cmd, str) and not shell:
        shell = True
    return subprocess.run(cmd, cwd=cwd, shell=shell, check=True, capture_output=True, env=env)
