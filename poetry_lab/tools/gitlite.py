"""git-lite tools: compare_versions, git_commit, git_log.

Git is always run as a fixed argument list (never through a shell), pinned to the
workspace's own repository, so agent text can only ever end up inside an argument.
"""

import os
import re
import shutil
import subprocess
from typing import Annotated

from pydantic import Field

from poetry_lab import config
from poetry_lab.sandbox import WORKSPACE_LOCK, WorkspaceError, safe_path

COMPARE_VERSIONS_DESCRIPTION = (
    "Show the git diff of ONE file between two commits of the workspace. Use it to see what "
    "changed in a poem, for example after another session edited it. from_ref is the older "
    "commit (default HEAD~1, the commit before the latest) and to_ref the newer (default HEAD). "
    "Refs can be HEAD, HEAD~2, a branch name or a short hash from git_log. Output is capped and "
    "marked truncated if long. Fails if path leaves the workspace, a ref is unknown or looks "
    "unsafe, or the workspace has fewer commits than the refs need."
)

GIT_COMMIT_DESCRIPTION = (
    "Commit ALL current workspace changes with one message and return the short commit hash. "
    "Use it after finishing a coherent piece of work, before updating CHECKPOINTS.md with that "
    "hash. Write a clear message of at most 500 characters. Fails if the message is empty, or "
    "if there is nothing to commit."
)

GIT_LOG_DESCRIPTION = (
    "List recent workspace commits as short hash, date and message, newest first. Use it to find "
    "refs for compare_versions or to see what earlier sessions did. Pass path to list only "
    "commits that touched one file. limit defaults to 10 (maximum 50). Returns an empty list "
    "if there are no matching commits. Fails if path leaves the workspace."
)

# Safe ref characters only: no leading '-', no spaces, no ':' and no '..'.
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./~^-]{0,99}$")
_SEP = "\x1f"


def _git_binary() -> str:
    found = shutil.which("git")
    if not found:
        raise WorkspaceError("git is not installed or not on PATH on the server.")
    return found


def _git_env() -> dict[str, str]:
    """Environment that pins git to the workspace repo and ignores user/system git config."""
    root = config.WORKSPACE_ROOT
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(
        GIT_DIR=str(root / ".git"),
        GIT_WORK_TREE=str(root),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
    )
    return env


def _clean_error(text: str) -> str:
    """First useful line of git's complaint, without server paths."""
    line = next((l.strip() for l in text.splitlines() if l.strip()), "unknown error")
    for private in (str(config.WORKSPACE_ROOT), str(config.WORKSPACE_ROOT).replace("\\", "/")):
        line = line.replace(private, "<workspace>")
    return line[:200]


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run one git command (argument list, no shell) in the workspace."""
    try:
        result = subprocess.run(
            [_git_binary(), *args],
            cwd=config.WORKSPACE_ROOT,
            env=_git_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise WorkspaceError("git took too long and was stopped.") from None
    except OSError:
        raise WorkspaceError("git could not be run on the server.") from None
    if check and result.returncode != 0:
        raise WorkspaceError(f"git failed: {_clean_error(result.stderr or result.stdout)}")
    return result


def ensure_workspace_repo() -> bool:
    """Create the workspace's own git repo if it has none. Returns True if it was created."""
    with WORKSPACE_LOCK:
        if (config.WORKSPACE_ROOT / ".git").exists():
            return False
        _git("init", "-q", "-b", "main")
        _git("config", "user.name", "Poetry Lab")
        _git("config", "user.email", "poetry-lab@localhost")
        _git("config", "core.autocrlf", "false")
        _git("config", "core.quotepath", "false")
        _git("add", "-A")
        _git("commit", "-q", "--no-verify", "--allow-empty", "-m", "Initial workspace snapshot")
        return True


def _check_ref(name: str, value: str) -> None:
    if not isinstance(value, str) or not _REF_RE.match(value) or ".." in value:
        raise WorkspaceError(
            f"{name} {value!r} is not a valid ref. Use HEAD, HEAD~1, a branch name or a hash from git_log."
        )


def _resolve_commit(name: str, ref: str) -> str:
    _check_ref(name, ref)
    result = _git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    full = result.stdout.strip()
    if result.returncode != 0 or not full:
        raise WorkspaceError(
            f"{name} {ref!r} does not exist. The workspace may have fewer commits; check git_log."
        )
    return full


def _short(full_hash: str) -> str:
    return _git("rev-parse", "--short", full_hash).stdout.strip()


def _relative_file(path: str) -> str:
    target = safe_path(path)
    rel = target.relative_to(config.WORKSPACE_ROOT).as_posix()
    if rel == ".":
        raise WorkspaceError("path must name a file, not the workspace root.")
    if target.is_dir():
        raise WorkspaceError(f"{path!r} is a folder. Give the path of one file.")
    return rel


def compare_versions(
    path: Annotated[str, Field(description="File path relative to the workspace root, e.g. poems/harbor-lantern.md")],
    from_ref: Annotated[str, Field(max_length=100, description="Older commit: HEAD~1, a hash or a branch.")] = "HEAD~1",
    to_ref: Annotated[str, Field(max_length=100, description="Newer commit: HEAD, a hash or a branch.")] = "HEAD",
) -> dict:
    """Diff of one file between two commits, capped in size."""
    rel = _relative_file(path)
    _check_ref("from_ref", from_ref)  # check every input before running any git command
    _check_ref("to_ref", to_ref)
    ensure_workspace_repo()
    old = _resolve_commit("from_ref", from_ref)
    new = _resolve_commit("to_ref", to_ref)
    diff = _git("diff", "--no-color", "--no-ext-diff", "--no-textconv", "-U3", old, new, "--", rel).stdout

    truncated = len(diff) > config.MAX_DIFF_CHARS
    if truncated:
        diff = diff[: config.MAX_DIFF_CHARS]
    return {
        "path": rel,
        "from": _short(old),
        "to": _short(new),
        "changed": bool(diff),
        "diff": diff if diff else "No changes to this file between the two commits.",
        "truncated": truncated,
    }


def git_commit(
    message: Annotated[str, Field(min_length=1, max_length=500, description="Commit message, 1 to 500 characters.")],
) -> dict:
    """Commit every workspace change and return the short hash."""
    if not isinstance(message, str) or not message.strip():
        raise WorkspaceError("Commit message must not be empty.")
    if len(message) > config.MAX_COMMIT_MESSAGE_CHARS:
        raise WorkspaceError(f"Commit message is too long; the limit is {config.MAX_COMMIT_MESSAGE_CHARS} characters.")
    if "\x00" in message:
        raise WorkspaceError("Commit message contains an invalid character.")

    with WORKSPACE_LOCK:
        ensure_workspace_repo()
        _git("add", "-A")
        staged = _git("diff", "--cached", "--no-renames", "--name-only").stdout.splitlines()
        if not staged:
            raise WorkspaceError("Nothing to commit: the workspace has no changes since the last commit.")
        _git("commit", "-q", "--no-verify", "-m", message.strip())
        short = _git("rev-parse", "--short", "HEAD").stdout.strip()
    return {"commit": short, "files_changed": len(staged), "message": message.strip().splitlines()[0][:100]}


def git_log(
    path: Annotated[str | None, Field(description="Optional file path; only commits touching it are listed.")] = None,
    limit: Annotated[int, Field(ge=1, le=50, description="How many commits to list (1 to 50).")] = 10,
) -> dict:
    """Recent commits: short hash, date, message."""
    if not 1 <= limit <= 50:
        raise WorkspaceError("limit must be between 1 and 50.")
    rel = _relative_file(path) if path else None
    ensure_workspace_repo()

    args = ["log", "-n", str(limit), "--date=format:%Y-%m-%d %H:%M", f"--pretty=format:%h{_SEP}%cd{_SEP}%s"]
    if rel:
        args += ["--", rel]
    out = _git(*args).stdout
    commits = []
    for line in out.splitlines():
        short, date, subject = (line.split(_SEP) + ["", ""])[:3]
        commits.append({"hash": short, "date": date, "message": subject})
    return {"commits": commits, "count": len(commits)}
