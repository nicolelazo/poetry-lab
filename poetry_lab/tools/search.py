"""search_poems: find lines containing a word, without returning whole files."""

import os
from pathlib import Path
from typing import Annotated

from pydantic import Field

from poetry_lab import config
from poetry_lab.sandbox import WRITABLE_SUFFIXES, SandboxError, WorkspaceError, safe_path

SEARCH_POEMS_DESCRIPTION = (
    "Case-insensitive text search across .md and .txt files in a folder (default 'poems'), "
    "including subfolders. Use it BEFORE read_file to find which poems contain a word or image, "
    "then read only those. Returns file, line number and the matching line only (long lines are "
    "cut at 200 characters), never whole files. 'truncated' is true if more matches exist than "
    "max_results. Fails if query is empty or over 200 characters, or the folder is missing or "
    "outside the workspace."
)

MAX_LINE_CHARS = 200


def search_poems(
    query: Annotated[str, Field(min_length=1, max_length=200, description="Text to look for (plain text, not a pattern).")],
    folder: Annotated[str, Field(description="Folder to search, relative to the workspace root.")] = "poems",
    max_results: Annotated[int, Field(ge=1, le=100, description="Maximum matching lines to return.")] = 20,
) -> dict:
    """Return matching lines as {file, line, text}."""
    needle = query.strip().lower()
    if not needle or len(query) > 200:
        raise WorkspaceError("query must be 1 to 200 characters and not blank.")
    if not 1 <= max_results <= 100:
        raise WorkspaceError("max_results must be between 1 and 100.")

    base = safe_path(folder)
    if not base.exists():
        raise WorkspaceError(f"Folder not found: {folder!r}")
    if not base.is_dir():
        raise WorkspaceError(f"Not a folder: {folder!r}. Use read_file for files.")

    root = config.WORKSPACE_ROOT
    matches: list[dict] = []
    truncated = False

    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d.lower() != ".git")
        for name in sorted(filenames):
            if not name.lower().endswith(WRITABLE_SUFFIXES):
                continue
            rel = (Path(dirpath) / name).relative_to(root).as_posix()
            try:
                file_path = safe_path(rel)  # skips symlinks that point outside the workspace
                if not file_path.is_file() or file_path.stat().st_size > config.MAX_FILE_BYTES:
                    continue
                text = file_path.read_bytes().decode("utf-8")
            except (SandboxError, OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if needle in line.lower():
                    if len(matches) >= max_results:
                        truncated = True
                        break
                    matches.append({"file": rel, "line": number, "text": line.strip()[:MAX_LINE_CHARS]})
            if truncated:
                break
        if truncated:
            break

    return {"query": query, "matches": matches, "truncated": truncated}
