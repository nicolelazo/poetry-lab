"""Reads settings from environment variables (loaded from .env if present)."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def _workspace_root() -> Path:
    raw = os.environ.get("WORKSPACE_ROOT", "sample_workspace")
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


WORKSPACE_ROOT: Path = _workspace_root()
MCP_HOST: str = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT: int = int(os.environ.get("MCP_PORT", "8000"))
MAX_FILE_BYTES: int = int(os.environ.get("MAX_FILE_BYTES", "102400"))
MCP_TOKEN: str = os.environ.get("MCP_TOKEN", "")


def _ngrok_domain() -> str:
    """Hostname only, e.g. 'name.ngrok-free.app' (strips any https:// or trailing slash)."""
    raw = os.environ.get("NGROK_DOMAIN", "").strip().lower()
    return raw.removeprefix("https://").removeprefix("http://").strip("/")


NGROK_DOMAIN: str = _ngrok_domain()
