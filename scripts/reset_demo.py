"""Put sample_workspace back to its committed state so the demo can be run again.

Restores tracked files from the code repo, removes files the demo created,
deletes the workspace's own inner git repo (the server recreates it) and
empties the call log. Only touches sample_workspace/ and logs/calls.jsonl.
Usage:  .venv\\Scripts\\python.exe scripts\\reset_demo.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "sample_workspace"
CALL_LOG = ROOT / "logs" / "calls.jsonl"


def git(*args: str) -> None:
    subprocess.run(["git", "-C", str(ROOT), *args], check=True)


def main() -> None:
    if not (ROOT / ".git").is_dir() or not WORKSPACE.is_dir():
        sys.exit("Run this from the poetry-lab project; sample_workspace/ was not found.")

    git("checkout", "--", "sample_workspace")
    git("clean", "-fd", "--", "sample_workspace")

    inner_git = WORKSPACE / ".git"
    if inner_git.is_dir() and inner_git.resolve().parent == WORKSPACE.resolve():
        shutil.rmtree(inner_git, ignore_errors=True)

    CALL_LOG.unlink(missing_ok=True)
    print("sample_workspace restored, workspace git repo removed (it is recreated on the next tool call), call log cleared.")


if __name__ == "__main__":
    main()
