"""Put sample_workspace back to its committed state so the demo can be run again.

Restores tracked files from the code repo, removes files the demo created,
deletes the workspace's own inner git repo (the server recreates it) and
empties the call log. Only touches sample_workspace/ and logs/calls.jsonl.
Usage:  .venv\\Scripts\\python.exe scripts\\reset_demo.py
"""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "sample_workspace"
CALL_LOG = ROOT / "logs" / "calls.jsonl"


def _make_writable_and_retry(func, path, _exc_info) -> None:
    """git marks its object files read-only on Windows; clear the flag and try again."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def git(*args: str) -> None:
    subprocess.run(["git", "-C", str(ROOT), *args], check=True)


def main() -> None:
    if not (ROOT / ".git").is_dir() or not WORKSPACE.is_dir():
        sys.exit("Run this from the poetry-lab project; sample_workspace/ was not found.")

    git("checkout", "--", "sample_workspace")
    git("clean", "-fd", "--", "sample_workspace")

    inner_git = WORKSPACE / ".git"
    if inner_git.is_dir() and inner_git.resolve().parent == WORKSPACE.resolve():
        shutil.rmtree(inner_git, onerror=_make_writable_and_retry)
        if inner_git.exists():
            sys.exit("Could not remove sample_workspace/.git. Close programs using it and run again.")

    CALL_LOG.unlink(missing_ok=True)

    # Recreate the workspace's own repo now, from the pristine files, so the demo's first
    # git_commit does not absorb the agent's changes into an "initial snapshot".
    os.environ["WORKSPACE_ROOT"] = str(WORKSPACE)
    sys.path.insert(0, str(ROOT))
    from poetry_lab.tools import gitlite

    gitlite.ensure_workspace_repo()
    print("sample_workspace restored, fresh workspace git repo created, call log cleared.")


if __name__ == "__main__":
    main()
