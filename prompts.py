PLAN_FILE_PROMPT = """You are a power programmer.
Create the EXACT contents for file "{path}" in a Python project.

Context:
- metaspec (YAML parsed): {metaspec_json}
- Purpose: {purpose}

Rules:
- Output ONLY the file content (no fences, no commentary).
- If tests/ files: make them runnable with pytest -q; avoid external deps.
- Keep code minimal, idiomatic, with helpful errors.
"""

AUTOFIX_PROMPT = """You are a senior engineer.
Tests failed. Propose minimal patches as JSON: {{"patches":[{{"path":"...","full_text":"..."}}]}}.
No commentary, no backticks.

Context:
- metaspec: {metaspec_json}
- failing logs (tail): {log_tail}
- sample file snippets:
{snippets}
"""
