"""The sandbox: turns an agent-supplied path into a safe real path, or refuses."""

from pathlib import Path, PurePosixPath, PureWindowsPath

from poetry_lab import config


WRITE_DIRS = ("poems", "notes", "feedback")
HANDOFF_FILES = ("PROJECT_STATE.md", "PLAN_LOG.md", "CHECKPOINTS.md", "DECISIONS.md")
WRITABLE_SUFFIXES = (".md", ".txt")


class WorkspaceError(ValueError):
    """A tool call failed for a reason the agent can fix. The message is safe to show."""


class SandboxError(WorkspaceError):
    """A path was rejected. The message is safe to show to the agent."""


def safe_path(rel: str, root: Path | None = None) -> Path:
    """Return the real path for `rel` inside the workspace root, or raise SandboxError.

    Every path from the agent is treated as relative to the root. The path is
    joined to the root and fully resolved (symlinks included), and the result
    must still be inside the root.
    """
    if root is None:
        root = config.WORKSPACE_ROOT
    root = root.resolve()

    if not isinstance(rel, str):
        raise SandboxError("Path must be a string.")
    if "\0" in rel:
        raise SandboxError("Path contains an invalid character.")

    # Treat Windows-style backslashes as separators on every OS.
    normalized = rel.replace("\\", "/")

    # Absolute paths (POSIX '/x', Windows 'C:/x', 'C:x', UNC '//host/x') are never allowed.
    if PurePosixPath(normalized).is_absolute() or PureWindowsPath(normalized).anchor:
        raise SandboxError("Absolute paths are not allowed. Use a path relative to the workspace root.")

    parts = [p for p in normalized.split("/") if p not in ("", ".")]

    # ':' would allow NTFS alternate data streams ('a:b.md') and drive tricks.
    if any(":" in p for p in parts):
        raise SandboxError("Path contains an invalid character ':'.")

    # The .git folder is never reachable through tools.
    if any(p.lower() == ".git" for p in parts):
        raise SandboxError("Access to .git is not allowed.")

    # Join, then resolve symlinks and '..'. strict=False so new files can be checked.
    resolved = (root / Path(*parts)).resolve() if parts else root

    if resolved != root and root not in resolved.parents:
        raise SandboxError("Path escapes the workspace root.")

    # A symlink could also point into .git, so check the resolved path again.
    if any(p.lower() == ".git" for p in resolved.relative_to(root).parts):
        raise SandboxError("Access to .git is not allowed.")

    return resolved


def relative_parts(path: Path, root: Path | None = None) -> tuple[str, ...]:
    """Parts of an already-resolved path relative to the workspace root."""
    root = (root or config.WORKSPACE_ROOT).resolve()
    return path.relative_to(root).parts


def check_write_zone(path: Path, root: Path | None = None) -> None:
    """Allow writes only in poems/, notes/, feedback/ and the four handoff files at the root.

    `path` must come from safe_path(), so symlinks are already resolved and the
    zone is judged on where the file really is.
    """
    parts = relative_parts(path, root)
    if len(parts) == 1 and parts[0] in HANDOFF_FILES:
        return
    if len(parts) >= 2 and parts[0] in WRITE_DIRS:
        return
    raise SandboxError(
        "Writes are only allowed in poems/, notes/, feedback/ and the files "
        + ", ".join(HANDOFF_FILES)
        + ". Everything else is read only."
    )


def check_writable_file(path: Path, root: Path | None = None) -> None:
    """Write zone check plus only .md and .txt files."""
    check_write_zone(path, root)
    if path.suffix.lower() not in WRITABLE_SUFFIXES:
        raise SandboxError("Only .md and .txt files can be written.")


def is_handoff_file(path: Path, root: Path | None = None) -> bool:
    parts = relative_parts(path, root)
    return len(parts) == 1 and parts[0] in HANDOFF_FILES
