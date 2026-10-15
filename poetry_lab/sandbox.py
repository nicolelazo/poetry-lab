"""The sandbox: turns an agent-supplied path into a safe real path, or refuses."""

from pathlib import Path, PurePosixPath, PureWindowsPath

from poetry_lab import config


class SandboxError(ValueError):
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
