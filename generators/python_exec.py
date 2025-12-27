import json
from pathlib import Path
from llm_providers import chat_once
from prompts import PLAN_FILE_PROMPT, AUTOFIX_PROMPT


def generate_files_from_metaspec(spec, proj_dir: Path, cfg):
    # requirements.txt
    reqs = sorted(set(spec["deps"].get("prod", []) + spec["deps"].get("dev", [])))
    print("[agent] Writing requirements.txt")
    (proj_dir / "requirements.txt").write_text(
        "\n".join(reqs) + ("\n" if reqs else "")
    )
    print("[agent] Wrote requirements.txt")

    # README scaffold
    print("[agent] Writing README.md")
    readme = f"# {spec['project']['name']}\n\n{spec['project']['summary']}\n"
    (proj_dir / "README.md").write_text(readme)
    print("[agent] Wrote README.md")

    # Files listed in metaspec
    for f in spec["files"]["include"]:
        path, purpose = f["path"], f.get("purpose", "")
        target = proj_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)

        print(f"[agent] Generating file: {path}")
        content = chat_once(
            cfg,
            [
                {
                    "role": "system",
                    "content": "Output only the complete file content, nothing else.",
                },
                {
                    "role": "user",
                    "content": PLAN_FILE_PROMPT.format(
                        path=path,
                        metaspec_json=json.dumps(spec),
                        purpose=purpose,
                    ),
                },
            ],
        )

        # Strip accidental fences
        c = content.strip()
        if c.startswith("```"):
            parts = c.split("```")
            c = parts[1 if len(parts) > 1 else 0]
            if (
                c.lower().startswith("python")
                or c.lower().startswith("json")
                or c.lower().startswith("yaml")
            ):
                c = c.split("\n", 1)[1] if "\n" in c else ""

        target.write_text(c)
        try:
            rel = target.relative_to(proj_dir)
        except ValueError:
            rel = target
        print(f"[agent] Wrote file: {rel}")


def attempt_autofix(spec, proj_dir: Path, cfg, last_report):
    print("[agent] Starting autofix attempt")
    tail = "\n".join(
        (s.get("notes", "") or "")[-800:] for s in last_report.get("stages", [])
    )
    snippets = _collect_snippets(proj_dir, 3500)
    resp = chat_once(
        cfg,
        [
            {"role": "system", "content": "Output only valid JSON with patches."},
            {
                "role": "user",
                "content": AUTOFIX_PROMPT.format(
                    metaspec_json=json.dumps(spec),
                    log_tail=tail[-1800:],
                    snippets=snippets,
                ),
            },
        ],
    )
    patches = _parse_patches(resp)
    for p in patches:
        tgt = proj_dir / p["path"]
        tgt.parent.mkdir(parents=True, exist_ok=True)
        print(f"[agent] Applying patch to: {p['path']}")
        tgt.write_text(p["full_text"])

    from buildrun.python_build import build_and_test

    print("[agent] Re-running build_and_test after autofix")
    return build_and_test(spec, proj_dir, cfg)


def _collect_snippets(root: Path, limit_chars: int):
    texts = []
    for p in list(root.rglob("*.py")) + list(root.rglob("*.md")):
        try:
            t = p.read_text()[:500]
            texts.append(f"--- {p.relative_to(root)} ---\n{t}")
        except Exception:
            pass
    joined = "\n".join(texts)
    return joined[:limit_chars]


def _parse_patches(resp: str):
    s = resp.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.lower().startswith(("json", "python")):
            s = s.split("\n", 1)[1] if "\n" in s else ""
    try:
        data = json.loads(s)
        return data.get("patches", [])
    except Exception:
        return []
