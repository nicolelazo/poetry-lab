"""Shared fixtures: a throwaway workspace per test, so tests never touch real files."""

import os
import subprocess

import pytest

from poetry_lab import config

HANDOFF = ("PROJECT_STATE.md", "PLAN_LOG.md", "CHECKPOINTS.md", "DECISIONS.md")


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """A small workspace. config.WORKSPACE_ROOT points at it for the duration of the test."""
    root = tmp_path / "ws"
    for folder in ("poems", "notes", "feedback", "trash", ".git"):
        (root / folder).mkdir(parents=True)
    (root / "poems" / "a.md").write_text("# A\nLantern light\nsecond line\n", encoding="utf-8")
    (root / "poems" / "b.md").write_text("# B\nthe lantern again\nLANTERN shouts\n", encoding="utf-8")
    (root / "poems" / "unique.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (root / "poems" / "crlf.md").write_bytes(b"first\r\nsecond\r\nthird\r\n")
    (root / "locked.md").write_text("read only", encoding="utf-8")
    (root / ".git" / "config").write_text("secret git config", encoding="utf-8")
    for name in HANDOFF:
        (root / name).write_text(f"# {name}\n", encoding="utf-8")
    monkeypatch.setattr(config, "WORKSPACE_ROOT", root.resolve())
    return root


@pytest.fixture
def git_ws(ws):
    """The workspace with a real git repo (replaces the fake .git folder) and one initial commit."""
    import shutil

    from poetry_lab.tools import gitlite

    shutil.rmtree(ws / ".git")
    assert gitlite.ensure_workspace_repo() is True
    return ws


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    """Send the call log to a temp folder outside the workspace."""
    folder = tmp_path / "logs"
    monkeypatch.setattr(config, "LOG_DIR", folder)
    return folder


@pytest.fixture
def outside(tmp_path):
    """A folder next to the workspace with a file the agent must never reach."""
    folder = tmp_path / "outside"
    folder.mkdir()
    (folder / "secret.txt").write_text("secret", encoding="utf-8")
    return folder


@pytest.fixture
def dir_link():
    """Make a directory link: a symlink if allowed, else a Windows junction, else skip."""

    def make(link, target):
        try:
            os.symlink(target, link, target_is_directory=True)
            return
        except (OSError, NotImplementedError):
            pass
        if os.name == "nt":
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True
            )
            if result.returncode == 0:
                return
        pytest.skip("Cannot create a symlink or junction here.")

    return make
