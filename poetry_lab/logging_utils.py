"""Call logger: appends one JSON line per tool call to logs/calls.jsonl (outside the workspace)."""

import functools
import inspect
import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from poetry_lab import config

# Arguments that hold poem text. Only their length is logged, never the text.
REDACTED_ARGS = ("content", "old_str", "new_str")
MAX_ARG_CHARS = 80
MAX_ERROR_CHARS = 200

_write_lock = threading.Lock()


def call_log_path() -> Path:
    return config.LOG_DIR / "calls.jsonl"


def verify_log_location() -> None:
    """Fail loudly if the log directory is inside the workspace, where agents could edit it."""
    log_dir = config.LOG_DIR.resolve()
    root = config.WORKSPACE_ROOT.resolve()
    if log_dir == root or root in log_dir.parents:
        raise RuntimeError("The log folder must be outside the workspace so agents cannot edit it.")


def summarize_args(arguments: dict) -> dict:
    """Short, safe description of the arguments: no poem text, long values cut."""
    summary = {}
    for name, value in arguments.items():
        if name in REDACTED_ARGS and isinstance(value, str):
            summary[name] = f"<{len(value)} chars>"
        elif isinstance(value, str):
            summary[name] = value if len(value) <= MAX_ARG_CHARS else value[:MAX_ARG_CHARS] + "..."
        else:
            summary[name] = value
    return summary


def write_entry(entry: dict) -> None:
    """Append one line. Logging problems must never break a tool call."""
    try:
        verify_log_location()
        path = call_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with _write_lock, open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception as err:  # noqa: BLE001 - deliberately broad, see docstring
        print(f"call log write failed: {type(err).__name__}", file=sys.stderr)


def logged(func):
    """Wrap a tool so each call is recorded with time, tool, args summary, ok/error and duration."""
    signature = inspect.signature(func)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            arguments = dict(signature.bind_partial(*args, **kwargs).arguments)
        except TypeError:
            arguments = dict(kwargs)
        started = time.perf_counter()
        error = None
        try:
            return func(*args, **kwargs)
        except Exception as err:
            error = f"{type(err).__name__}: {err}"[:MAX_ERROR_CHARS]
            raise
        finally:
            write_entry(
                {
                    "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "tool": func.__name__,
                    "args": summarize_args(arguments),
                    "ok": error is None,
                    "error": error,
                    "ms": round((time.perf_counter() - started) * 1000),
                }
            )

    return wrapper
