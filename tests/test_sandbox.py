import pytest

from poetry_lab.sandbox import (
    SandboxError,
    check_write_zone,
    check_writable_file,
    is_handoff_file,
    safe_path,
)


def test_root_and_dot(ws):
    assert safe_path(".", ws) == ws.resolve()
    assert safe_path("", ws) == ws.resolve()


def test_normal_relative_paths(ws):
    assert safe_path("poems/a.md", ws) == (ws / "poems" / "a.md").resolve()
    assert safe_path("poems/new.md", ws) == (ws / "poems" / "new.md").resolve()  # not created yet
    assert safe_path("poems/../poems/a.md", ws) == (ws / "poems" / "a.md").resolve()  # stays inside


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
        "C:win.ini",
        "\\\\server\\share\\x",
        "x\0y",
        "poems/a:hidden.md",
    ],
)
def test_escapes_rejected(ws, bad):
    with pytest.raises(SandboxError):
        safe_path(bad, ws)


def test_absolute_path_to_real_outside_file_rejected(ws, outside):
    with pytest.raises(SandboxError):
        safe_path(str(outside / "secret.txt"), ws)


@pytest.mark.parametrize("bad", [".git", ".git/config", "poems/../.git/HEAD", ".GIT/config"])
def test_git_folder_rejected(ws, bad):
    with pytest.raises(SandboxError):
        safe_path(bad, ws)


def test_symlink_escape_rejected(ws, outside, dir_link):
    dir_link(ws / "poems" / "link", outside)
    with pytest.raises(SandboxError):
        safe_path("poems/link/secret.txt", ws)
    with pytest.raises(SandboxError):
        safe_path("poems/link", ws)


def test_symlink_to_git_rejected(ws, dir_link):
    dir_link(ws / "poems" / "gitlink", ws / ".git")
    with pytest.raises(SandboxError):
        safe_path("poems/gitlink/config", ws)


def test_symlink_inside_root_allowed(ws, dir_link):
    dir_link(ws / "alias", ws / "poems")
    assert safe_path("alias/a.md", ws) == (ws / "poems" / "a.md").resolve()


# ---- write zones ----

@pytest.mark.parametrize(
    "ok",
    ["poems/x.md", "notes/x.txt", "feedback/x.md", "poems/sub/x.md", "PROJECT_STATE.md", "DECISIONS.md"],
)
def test_write_zone_allows(ws, ok):
    check_writable_file(safe_path(ok, ws), ws)


# Note: on Windows 'Poems/x.md' resolves to the real 'poems/' folder, so it is judged as poems/.
@pytest.mark.parametrize("bad", ["locked.md", "trash/x.md", "newroot.md", "poems", "x/poems/y.md"])
def test_write_zone_blocks(ws, bad):
    with pytest.raises(SandboxError):
        check_write_zone(safe_path(bad, ws), ws)


@pytest.mark.parametrize("bad", ["poems/x.py", "poems/x", "poems/x.md.exe", "poems/x.MD.bak"])
def test_extension_blocks(ws, bad):
    with pytest.raises(SandboxError):
        check_writable_file(safe_path(bad, ws), ws)


def test_write_zone_judged_on_real_location(ws, dir_link):
    dir_link(ws / "poems" / "to_trash", ws / "trash")
    with pytest.raises(SandboxError):
        check_write_zone(safe_path("poems/to_trash/x.md", ws), ws)


def test_is_handoff_file(ws):
    assert is_handoff_file(safe_path("PLAN_LOG.md", ws), ws)
    assert not is_handoff_file(safe_path("poems/PLAN_LOG.md", ws), ws)
