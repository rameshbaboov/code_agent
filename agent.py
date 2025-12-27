import json, shutil, subprocess, sys
from pathlib import Path
import yaml
from rich import print
from metaspec_loader import load_and_validate
from generators.python_exec import generate_files_from_metaspec
from buildrun.python_build import build_and_test
from llm_providers import chat_once

def main():
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    spec = load_and_validate("metaspec.yaml")
    out_root = Path(cfg["project_root"]).resolve()
    proj_dir = out_root / spec["project"]["name"]
    if proj_dir.exists():
        shutil.rmtree(proj_dir)
    proj_dir.mkdir(parents=True)
    (proj_dir/"tests").mkdir(parents=True, exist_ok=True)
    (proj_dir/"src").mkdir(parents=True, exist_ok=True)

    # Generate exact files
    print("[bold cyan]Generating files...[/bold cyan]")
    generate_files_from_metaspec(spec, proj_dir, cfg)

    # Build & test
    print("[bold cyan]Build & Test...[/bold cyan]")
    ok, report = build_and_test(spec, proj_dir, cfg)

    # Optional autofix loop
    iters = cfg.get("autofix",{}).get("max_iterations",0)
    for i in range(iters):
        if ok: break
        print(f"[yellow]Autofix round {i+1}[/yellow]")
        from generators.python_exec import attempt_autofix
        ok, report = attempt_autofix(spec, proj_dir, cfg, last_report=report)

    (proj_dir/"autogen-report.json").write_text(json.dumps(report, indent=2))
    print(f"\n[bold]{'✅ PASS' if ok else '❌ FAIL'}[/bold]  Project at: {proj_dir}")

if __name__ == "__main__":
    main()
