"""File tools. In M1 this holds only list_files."""

from poetry_lab import config
from poetry_lab.sandbox import SandboxError, safe_path

LIST_FILES_DESCRIPTION = (
    "List the names inside one folder of the poetry workspace. "
    "Use it first to see what exists, for example folder='poems' or folder='.'. "
    "Folder names end with '/'. Returns names only, not file contents. "
    "Fails if the folder does not exist, is not a folder, or the path leaves the workspace "
    "(absolute paths, '..' and .git are rejected)."
)


def list_files(folder: str = ".") -> list[str]:
    """Return sorted names in `folder` (relative to the workspace root); folders end with '/'."""
    path = safe_path(folder)
    if not path.exists():
        raise SandboxError(f"Folder not found: {folder!r}")
    if not path.is_dir():
        raise SandboxError(f"Not a folder: {folder!r}. Use read_file for files.")

    names = []
    for entry in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if entry.name.lower() == ".git":
            continue
        names.append(entry.name + "/" if entry.is_dir() else entry.name)
    return names
