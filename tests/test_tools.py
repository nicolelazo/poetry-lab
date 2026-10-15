import pytest

from poetry_lab import config
from poetry_lab.sandbox import SandboxError
from poetry_lab.tools.files import list_files


@pytest.fixture
def ws(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    (root / "poems").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "poems" / "b.md").write_text("b", encoding="utf-8")
    (root / "poems" / "a.md").write_text("a", encoding="utf-8")
    (root / "DECISIONS.md").write_text("d", encoding="utf-8")
    monkeypatch.setattr(config, "WORKSPACE_ROOT", root.resolve())
    return root


def test_list_root_marks_folders_and_hides_git(ws):
    assert list_files(".") == ["DECISIONS.md", "poems/"]


def test_list_folder_is_sorted(ws):
    assert list_files("poems") == ["a.md", "b.md"]


def test_default_folder_is_root(ws):
    assert list_files() == list_files(".")


@pytest.mark.parametrize("bad", ["../x", "/etc", "C:\\Windows", ".git", "missing", "DECISIONS.md"])
def test_list_files_errors(ws, bad):
    with pytest.raises(SandboxError):
        list_files(bad)


def test_sample_workspace_lists_three_poems(monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE_ROOT", (config.PROJECT_ROOT / "sample_workspace").resolve())
    assert list_files("poems") == ["harbor-lantern.md", "paper-moths.md", "winter-bread.md"]
