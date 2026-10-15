"""File tools: list_files, read_file, write_file, str_replace, delete_file."""

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated

from pydantic import Field

from poetry_lab import config
from poetry_lab.sandbox import (
    WorkspaceError,
    check_writable_file,
    check_write_zone,
    is_handoff_file,
    safe_path,
)

LIST_FILES_DESCRIPTION = (
    "List the names inside one folder of the poetry workspace. "
    "Use it first to see what exists, for example folder='poems' or folder='.'. "
    "Folder names end with '/'. Returns names only, not file contents. "
    "Fails if the folder does not exist, is not a folder, or the path leaves the workspace "
    "(absolute paths, '..' and .git are rejected)."
)

READ_FILE_DESCRIPTION = (
    "Read a slice of one text file. Use it to read a poem or a handoff file after finding it "
    "with list_files or search_poems. Returns the lines start_line to start_line+max_lines-1, "
    "the total line count and a 'version' hash; pass that hash as if_version to write_file to "
    "avoid overwriting someone else's change. Keep max_lines small and page through long files. "
    "Fails if the file is missing, is a folder, is larger than 100 KB, is not UTF-8 text, "
    "or start_line is past the end."
)

WRITE_FILE_DESCRIPTION = (
    "Create a new file or fully replace an existing one. Use it for new notes or feedback files; "
    "for small edits to an existing poem use str_replace instead. Only .md and .txt files in "
    "poems/, notes/, feedback/ and the four handoff files (PROJECT_STATE.md, PLAN_LOG.md, "
    "CHECKPOINTS.md, DECISIONS.md) can be written, up to 100 KB. If you pass if_version (from "
    "read_file) and the file changed since, the write is refused and the current version is "
    "reported. Fails outside the write zones, for other extensions, or for content over 100 KB."
)

STR_REPLACE_DESCRIPTION = (
    "Replace exactly one occurrence of old_str with new_str in a file. Use it for small, "
    "targeted edits after read_file. old_str must appear exactly once or the call fails: if it "
    "appears 0 times check the exact text, if more than once widen old_str with surrounding "
    "text. Same write zones, extensions and size limit as write_file. Fails if old_str is empty."
)

DELETE_FILE_DESCRIPTION = (
    "Move one file to trash/ with a timestamp. It is never erased, so a mistake can be undone by "
    "a human. Use it only when the owner asked to remove a file. Only files in the write zones "
    "can be deleted. The four handoff files can never be deleted. Fails if the file does not "
    "exist or is a folder."
)


def _version(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _rel(path: Path) -> str:
    """Workspace-relative path with forward slashes, for showing to the agent."""
    return path.relative_to(config.WORKSPACE_ROOT).as_posix()


def _load(path: Path, shown: str) -> tuple[bytes, str]:
    """Read a file as UTF-8 text, enforcing the size limit. Returns (raw bytes, text)."""
    if not path.exists():
        raise WorkspaceError(f"File not found: {shown!r}")
    if not path.is_file():
        raise WorkspaceError(f"Not a file: {shown!r}. Use list_files for folders.")
    limit = config.MAX_FILE_BYTES
    if path.stat().st_size > limit:
        raise WorkspaceError(f"File {shown!r} is larger than the {limit} byte limit.")
    try:
        data = path.read_bytes()
    except OSError:
        raise WorkspaceError(f"Could not read {shown!r}.") from None
    try:
        return data, data.decode("utf-8")
    except UnicodeDecodeError:
        raise WorkspaceError(f"{shown!r} is not valid UTF-8 text.") from None


def _atomic_write(path: Path, data: bytes) -> None:
    """Write via a temp file and rename, so a crash never leaves a half-written poem."""
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise WorkspaceError(f"Could not write {path.name!r}.") from None


def _check_size(data: bytes) -> None:
    if len(data) > config.MAX_FILE_BYTES:
        raise WorkspaceError(
            f"Content is {len(data)} bytes; the limit is {config.MAX_FILE_BYTES} bytes."
        )


def list_files(folder: Annotated[str, Field(description="Folder relative to the workspace root.")] = ".") -> list[str]:
    """Return sorted names in `folder` (relative to the workspace root); folders end with '/'."""
    path = safe_path(folder)
    if not path.exists():
        raise WorkspaceError(f"Folder not found: {folder!r}")
    if not path.is_dir():
        raise WorkspaceError(f"Not a folder: {folder!r}. Use read_file for files.")

    names = []
    for entry in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if entry.name.lower() == ".git":
            continue
        names.append(entry.name + "/" if entry.is_dir() else entry.name)
    return names


def read_file(
    path: Annotated[str, Field(description="File path relative to the workspace root, e.g. poems/harbor-lantern.md")],
    start_line: Annotated[int, Field(ge=1, description="First line to return (1-based).")] = 1,
    max_lines: Annotated[int, Field(ge=1, le=500, description="Maximum number of lines to return.")] = 200,
) -> dict:
    """Return a slice of a text file plus total line count and content version."""
    if start_line < 1 or not 1 <= max_lines <= 500:
        raise WorkspaceError("start_line must be >= 1 and max_lines must be between 1 and 500.")
    target = safe_path(path)
    data, text = _load(target, path)
    lines = text.splitlines()
    total = len(lines)
    if total and start_line > total:
        raise WorkspaceError(f"start_line {start_line} is past the end; the file has {total} lines.")
    chunk = lines[start_line - 1 : start_line - 1 + max_lines]
    return {
        "path": _rel(target),
        "content": "\n".join(chunk),
        "start_line": start_line,
        "end_line": start_line + len(chunk) - 1 if chunk else start_line - 1,
        "total_lines": total,
        "version": _version(data),
    }


def write_file(
    path: Annotated[str, Field(description="Target .md or .txt path inside poems/, notes/, feedback/ or a handoff file.")],
    content: Annotated[str, Field(description="Full new content of the file.")],
    if_version: Annotated[str | None, Field(description="Version hash from read_file; write only if unchanged.")] = None,
) -> dict:
    """Create or replace a file inside a write zone."""
    target = safe_path(path)
    check_writable_file(target)
    data = content.encode("utf-8")
    _check_size(data)

    existed = target.exists()
    if existed and not target.is_file():
        raise WorkspaceError(f"Not a file: {path!r}.")
    if if_version is not None:
        if not existed:
            raise WorkspaceError(f"if_version was given but {path!r} does not exist yet. Omit if_version to create it.")
        current = _version(_load(target, path)[0])
        if current != if_version:
            raise WorkspaceError(
                f"Version mismatch: {path!r} changed since you read it. "
                f"Current version is {current}. Read the file again before writing."
            )

    _atomic_write(target, data)
    return {"path": _rel(target), "created": not existed, "bytes": len(data), "version": _version(data)}


def _match_line_endings(text: str, s: str) -> str:
    """read_file shows lines joined by \\n; if the file uses CRLF, convert the agent's strings to match."""
    if "\r\n" in text:
        return s.replace("\r\n", "\n").replace("\n", "\r\n")
    return s


def str_replace(
    path: Annotated[str, Field(description="Existing .md or .txt file inside a write zone.")],
    old_str: Annotated[str, Field(min_length=1, description="Exact text to replace; must occur exactly once.")],
    new_str: Annotated[str, Field(description="Replacement text (may be empty to delete old_str).")],
) -> dict:
    """Replace exactly one occurrence of old_str with new_str."""
    target = safe_path(path)
    check_writable_file(target)
    if old_str == "":
        raise WorkspaceError("old_str must not be empty.")
    _, text = _load(target, path)

    old = _match_line_endings(text, old_str)
    new = _match_line_endings(text, new_str)
    count = text.count(old)
    if count == 0:
        raise WorkspaceError(f"old_str was not found in {path!r}. Check the exact text with read_file.")
    if count > 1:
        raise WorkspaceError(
            f"old_str appears {count} times in {path!r}. Add surrounding text so it matches exactly once."
        )

    line = text[: text.index(old)].count("\n") + 1
    data = text.replace(old, new, 1).encode("utf-8")
    _check_size(data)
    _atomic_write(target, data)
    return {"path": _rel(target), "replaced_at_line": line, "version": _version(data)}


def delete_file(
    path: Annotated[str, Field(description="File inside a write zone to move to trash/.")],
) -> dict:
    """Move a file to trash/ with a timestamp. Handoff files are protected."""
    target = safe_path(path)
    if is_handoff_file(target):
        raise WorkspaceError("The four handoff files cannot be deleted.")
    check_write_zone(target)
    if not target.exists():
        raise WorkspaceError(f"File not found: {path!r}")
    if not target.is_file():
        raise WorkspaceError(f"Not a file: {path!r}. Only single files can be deleted.")

    trash = config.WORKSPACE_ROOT / "trash"
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    flat = _rel(target).replace("/", "__")
    dest = trash / f"{stamp}_{flat}"
    n = 1
    while dest.exists():
        dest = trash / f"{stamp}_{n}_{flat}"
        n += 1
    try:
        trash.mkdir(exist_ok=True)
        os.replace(target, dest)
    except OSError:
        raise WorkspaceError(f"Could not move {path!r} to trash.") from None
    return {"deleted": _rel(target), "moved_to": _rel(dest)}
