import subprocess

import pytest

from poetry_lab import config
from poetry_lab.sandbox import WorkspaceError
from poetry_lab.tools import gitlite
from poetry_lab.tools.files import delete_file, str_replace, write_file
from poetry_lab.tools.gitlite import compare_versions, git_commit, git_log

BAD_REFS = ["--output=x", "-p", "--help", "HEAD; echo hi", "HEAD && dir", "$(whoami)", "HEAD..HEAD~1",
            "", " ", "HEAD~1 HEAD", "HEAD:poems/a.md", "`id`", "a" * 101, "@{0}", "HEAD\nHEAD"]


def real_git(ws, *args):
    """Run git directly in a test workspace to check what the tools did."""
    result = subprocess.run(["git", *args], cwd=ws, capture_output=True, text=True,
                            env={**__import__("os").environ, "GIT_DIR": str(ws / ".git"), "GIT_WORK_TREE": str(ws)})
    return result.stdout.strip()


# ---------- workspace repo ----------

def test_ensure_repo_creates_it_with_initial_commit(git_ws):
    assert (git_ws / ".git").is_dir()
    assert git_log()["commits"][0]["message"] == "Initial workspace snapshot"
    assert real_git(git_ws, "config", "user.name") == "Poetry Lab"
    assert real_git(git_ws, "ls-files").count("poems/a.md") == 1


def test_ensure_repo_is_idempotent(git_ws):
    assert gitlite.ensure_workspace_repo() is False
    assert git_log()["count"] == 1


def test_repo_is_created_on_demand_by_the_tools(ws):
    import shutil
    shutil.rmtree(ws / ".git")
    assert git_log()["count"] == 1
    assert (ws / ".git").is_dir()


def test_workspace_repo_is_separate_from_an_outer_repo(tmp_path, monkeypatch):
    outer = tmp_path / "outer"
    inner = outer / "workspace"
    inner.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(outer)], check=True)
    (inner / "poems").mkdir()
    (inner / "poems" / "a.md").write_text("one\n", encoding="utf-8")
    monkeypatch.setattr(config, "WORKSPACE_ROOT", inner.resolve())

    assert gitlite.ensure_workspace_repo() is True
    write_file("poems/b.md", "two\n")
    git_commit("add b")

    assert (inner / ".git").is_dir()
    assert git_log()["count"] == 2
    outer_commits = subprocess.run(["git", "-C", str(outer), "rev-list", "--all", "--count"],
                                   capture_output=True, text=True).stdout.strip()
    assert outer_commits == "0"  # the outer repo was never committed to


# ---------- git_commit ----------

def test_commit_returns_short_hash_and_is_logged(git_ws):
    write_file("feedback/r1.md", "Lantern recurs.\n")
    result = git_commit("Add first review")
    assert len(result["commit"]) >= 7 and result["files_changed"] == 1
    assert result["commit"] == real_git(git_ws, "rev-parse", "--short", "HEAD")
    assert git_log()["commits"][0]["message"] == "Add first review"


def test_commit_includes_edits_new_files_and_trash_moves(git_ws):
    str_replace("poems/a.md", "Lantern light", "Candle light")
    write_file("notes/n.md", "note\n")
    delete_file("poems/unique.txt")
    result = git_commit("mixed changes")
    assert result["files_changed"] == 4  # a.md, n.md, unique.txt removed, trash copy added
    assert real_git(git_ws, "status", "--porcelain") == ""


def test_commit_with_nothing_changed_fails(git_ws):
    with pytest.raises(WorkspaceError, match="Nothing to commit"):
        git_commit("no changes")
    assert git_log()["count"] == 1


@pytest.mark.parametrize("bad", ["", "   ", "\n\t", "x" * 501, "bad\x00msg"])
def test_commit_rejects_bad_messages(git_ws, bad):
    write_file("notes/n.md", "note\n")
    with pytest.raises(WorkspaceError):
        git_commit(bad)
    assert git_log()["count"] == 1


@pytest.mark.parametrize("message", ["--amend", "-m evil", '"; echo pwned > hacked.txt; "', "a && del x", "$(id)", "`id`"])
def test_commit_message_is_data_never_a_command(git_ws, message):
    write_file("notes/n.md", f"note for {abs(hash(message))}\n")
    git_commit(message)
    assert git_log()["commits"][0]["message"] == message.strip()
    assert not (git_ws / "hacked.txt").exists()


def test_commit_message_with_multiple_lines(git_ws):
    write_file("notes/n.md", "note\n")
    git_commit("Subject line\n\nBody line")
    assert git_log()["commits"][0]["message"] == "Subject line"


# ---------- git_log ----------

def test_log_lists_newest_first_with_date(git_ws):
    for i in range(3):
        write_file(f"notes/n{i}.md", f"{i}\n")
        git_commit(f"commit {i}")
    commits = git_log()["commits"]
    assert [c["message"] for c in commits] == ["commit 2", "commit 1", "commit 0", "Initial workspace snapshot"]
    assert all(len(c["hash"]) >= 7 and len(c["date"]) == 16 for c in commits)


def test_log_limit(git_ws):
    for i in range(3):
        write_file(f"notes/n{i}.md", f"{i}\n")
        git_commit(f"commit {i}")
    assert git_log(limit=2)["count"] == 2


def test_log_for_one_file(git_ws):
    write_file("notes/n.md", "n\n")
    git_commit("touch n")
    write_file("poems/a.md", "changed\n")
    git_commit("touch a")
    assert [c["message"] for c in git_log(path="notes/n.md")["commits"]] == ["touch n"]


def test_log_for_file_with_no_history_is_empty(git_ws):
    assert git_log(path="poems/never-existed.md") == {"commits": [], "count": 0}


@pytest.mark.parametrize("limit", [0, -1, 51, 1000])
def test_log_limit_out_of_range(git_ws, limit):
    with pytest.raises(WorkspaceError):
        git_log(limit=limit)


@pytest.mark.parametrize("bad", ["../x", "/etc/passwd", "C:\\Windows\\win.ini", ".git/config", ".git", "poems"])
def test_log_bad_paths(git_ws, bad):
    with pytest.raises(WorkspaceError):
        git_log(path=bad)


# ---------- compare_versions ----------

@pytest.fixture
def edited(git_ws):
    str_replace("poems/a.md", "Lantern light", "Candle light")
    git_commit("soften line 2")
    return git_ws


def test_compare_defaults_show_the_last_change(edited):
    r = compare_versions("poems/a.md")
    assert r["changed"] is True and r["truncated"] is False
    assert "-Lantern light" in r["diff"] and "+Candle light" in r["diff"]
    assert r["path"] == "poems/a.md"


def test_compare_with_hashes_and_head_forms(edited):
    first = git_log()["commits"][1]["hash"]
    last = git_log()["commits"][0]["hash"]
    assert compare_versions("poems/a.md", from_ref=first, to_ref=last)["changed"] is True
    assert compare_versions("poems/a.md", from_ref="HEAD~1", to_ref="HEAD")["changed"] is True
    assert compare_versions("poems/a.md", from_ref="HEAD", to_ref="HEAD~1")["diff"].startswith("diff --git")


def test_compare_unchanged_file_says_so(edited):
    r = compare_versions("poems/b.md")
    assert r["changed"] is False and "No changes" in r["diff"]


def test_compare_new_file_shows_additions(git_ws):
    write_file("notes/new.md", "fresh\n")
    git_commit("add new")
    assert "+fresh" in compare_versions("notes/new.md")["diff"]


def test_compare_output_is_capped(edited, monkeypatch):
    monkeypatch.setattr(config, "MAX_DIFF_CHARS", 40)
    r = compare_versions("poems/a.md")
    assert r["truncated"] is True and len(r["diff"]) == 40


def test_compare_with_only_one_commit_gives_clear_error(git_ws):
    with pytest.raises(WorkspaceError, match="does not exist"):
        compare_versions("poems/a.md")  # default from_ref HEAD~1 has nothing behind it


def test_compare_unknown_ref(edited):
    with pytest.raises(WorkspaceError, match="does not exist"):
        compare_versions("poems/a.md", from_ref="deadbeef")
    with pytest.raises(WorkspaceError, match="does not exist"):
        compare_versions("poems/a.md", to_ref="no-such-branch")


@pytest.mark.parametrize("ref", BAD_REFS)
def test_compare_rejects_unsafe_refs_before_running_git(edited, ref, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("git must not run for an unsafe ref")

    monkeypatch.setattr(gitlite.subprocess, "run", boom)
    with pytest.raises(WorkspaceError, match="not a valid ref"):
        compare_versions("poems/a.md", from_ref=ref)
    with pytest.raises(WorkspaceError, match="not a valid ref"):
        compare_versions("poems/a.md", to_ref=ref)


@pytest.mark.parametrize("bad", ["../x", "poems/../../x", "..\\x", "/etc/passwd", "C:\\Windows\\win.ini", ".git/config", ".git"])
def test_compare_path_escapes(edited, bad):
    with pytest.raises(WorkspaceError):
        compare_versions(bad)


@pytest.mark.parametrize("bad", [".", "", "poems"])
def test_compare_needs_a_file(edited, bad):
    with pytest.raises(WorkspaceError):
        compare_versions(bad)


# ---------- subprocess safety ----------

def test_git_is_always_called_with_a_list_and_no_shell(git_ws, monkeypatch):
    calls = []
    real_run = subprocess.run

    def spy(cmd, *args, **kwargs):
        calls.append((cmd, kwargs))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(gitlite.subprocess, "run", spy)
    write_file("notes/n.md", '"; rm -rf / ; "\n')
    git_commit('"; rm -rf / ; "')
    git_log(path="notes/n.md")
    compare_versions("notes/n.md", from_ref="HEAD~1", to_ref="HEAD")

    assert len(calls) > 5
    for cmd, kwargs in calls:
        assert isinstance(cmd, list) and all(isinstance(part, str) for part in cmd)
        assert not kwargs.get("shell", False)
        assert kwargs["env"]["GIT_DIR"].endswith(".git") and kwargs["env"]["GIT_WORK_TREE"] == str(git_ws)
        assert kwargs["timeout"] == config.GIT_TIMEOUT_SECONDS
    assert not (git_ws / "hacked").exists()


def test_environment_ignores_outer_git_variables(git_ws, monkeypatch):
    monkeypatch.setenv("GIT_DIR", "C:/somewhere/else/.git")
    monkeypatch.setenv("GIT_INDEX_FILE", "C:/other/index")
    env = gitlite._git_env()
    assert env["GIT_DIR"] == str(git_ws / ".git") and "GIT_INDEX_FILE" not in env
    assert git_log()["count"] == 1


def test_missing_git_binary_gives_a_clean_error(git_ws, monkeypatch):
    monkeypatch.setattr(gitlite.shutil, "which", lambda name: None)
    with pytest.raises(WorkspaceError, match="not installed"):
        git_log()


def test_git_failures_are_clean_and_hide_server_paths(git_ws):
    (git_ws / ".git" / "HEAD").write_text("garbage", encoding="utf-8")
    with pytest.raises(WorkspaceError) as err:
        git_log()
    text = str(err.value)
    assert "Traceback" not in text and str(git_ws) not in text
