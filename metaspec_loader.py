from pathlib import Path
import yaml, sys

REQUIRED_TOP = ["version","project","stack","deps","files","acceptance","build"]

def load_and_validate(path:str):
    y = yaml.safe_load(Path(path).read_text())
    miss = [k for k in REQUIRED_TOP if k not in y]
    if miss:
        raise SystemExit(f"metaspec missing keys: {miss}")
    if y["project"]["language"] != "python":
        raise SystemExit("MVP supports python only for now.")
    if y["stack"]["entry_type"] == "cli" and not y.get("cli",{}).get("commands"):
        raise SystemExit("entry_type=cli but cli.commands missing")
    return y
