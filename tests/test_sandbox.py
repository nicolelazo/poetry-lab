import os
import subprocess

import pytest

from poetry_lab.sandbox import SandboxError, safe_path


@pytest.fixture
def root(tmp_path):
    ws = tmp_path / "ws"
    (ws / "poems").mkdir(parents=True)
    (ws / "poems" / "a.md").write_text("hi", encoding="utf-8")
    (ws / ".git").mkdir()
    return ws


def test_root_and_dot(root):
    assert safe_path(".", root) == root.resolve()
    assert safe_path("", root) == root.resolve()


def test_normal_relative_paths(root):
    assert safe_path("poems/a.md", root) == (root / "poems" / "a.md").resolve()
    assert safe_path("poems/new.md", root) == (root / "poems" / "new.md").resolve()  # not created yet
    assert safe_path("poems/../poems/a.md", root) == (root / "poems" / "a.md").resolve()  # stays inside


@pytest.mark.parametrize(
    "bad",
    [
        "../x",
        "poems/../../x",
        "..\\x",
        "poems\\..\\..\\x",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "C:/Windows/win.ini",
        "\\\\server\\share\\x",
        "x\0y",
    ],
)
def test_escapes_rejected(root, bad):
    with pytest.raises(SandboxError):
        safe_path(bad, root)


def test_absolute_path_to_real_outside_file_rejected(root, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(SandboxError):
        safe_path(str(outside), root)


@pytest.mark.parametrize("bad", [".git", ".git/config", "poems/../.git/HEAD", ".GIT/config"])
def test_git_folder_rejected(root, bad):
    with pytest.raises(SandboxError):
        safe_path(bad, root)


def make_dir_link(link, target):
    """Symlink if allowed, else a Windows junction (needs no special rights). Skip if neither works."""
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


def test_symlink_escape_rejected(root, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = root / "poems" / "link"
    make_dir_link(link, outside)
    with pytest.raises(SandboxError):
        safe_path("poems/link/secret.txt", root)
    with pytest.raises(SandboxError):
        safe_path("poems/link", root)


def test_symlink_inside_root_allowed(root):
    link = root / "alias"
    make_dir_link(link, root / "poems")
    assert safe_path("alias/a.md", root) == (root / "poems" / "a.md").resolve()
