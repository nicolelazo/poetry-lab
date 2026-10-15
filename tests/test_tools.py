import asyncio

import pytest

from poetry_lab import config
from poetry_lab.sandbox import SandboxError, WorkspaceError
from poetry_lab.tools.files import delete_file, list_files, read_file, str_replace, write_file
from poetry_lab.tools.search import search_poems

ESCAPES = ["../x", "poems/../../x", "..\\x", "/etc/passwd", "C:\\Windows\\win.ini", ".git/config"]


# ---------- list_files ----------

def test_list_root_marks_folders_and_hides_git(ws):
    names = list_files(".")
    assert "poems/" in names and "DECISIONS.md" in names and ".git/" not in names


def test_list_folder_is_sorted(ws):
    assert list_files("poems") == ["a.md", "b.md", "crlf.md", "unique.txt"]


def test_list_default_folder_is_root(ws):
    assert list_files() == list_files(".")


@pytest.mark.parametrize("bad", ESCAPES + ["missing", "locked.md"])
def test_list_files_errors(ws, bad):
    with pytest.raises(WorkspaceError):
        list_files(bad)


def test_sample_workspace_lists_three_poems(monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE_ROOT", (config.PROJECT_ROOT / "sample_workspace").resolve())
    assert list_files("poems") == ["harbor-lantern.md", "paper-moths.md", "winter-bread.md"]


# ---------- read_file ----------

def test_read_whole_small_file(ws):
    r = read_file("poems/a.md")
    assert r["content"] == "# A\nLantern light\nsecond line"
    assert (r["start_line"], r["end_line"], r["total_lines"]) == (1, 3, 3)
    assert len(r["version"]) == 16


def test_read_slice(ws):
    r = read_file("poems/unique.txt", start_line=2, max_lines=1)
    assert r["content"] == "two" and r["end_line"] == 2 and r["total_lines"] == 3


def test_read_version_changes_with_content(ws):
    before = read_file("poems/a.md")["version"]
    (ws / "poems" / "a.md").write_text("changed", encoding="utf-8")
    assert read_file("poems/a.md")["version"] != before


def test_read_empty_file(ws):
    (ws / "notes" / "empty.md").write_text("", encoding="utf-8")
    r = read_file("notes/empty.md")
    assert r["content"] == "" and r["total_lines"] == 0


def test_read_works_outside_write_zones(ws):
    assert read_file("locked.md")["content"] == "read only"


def test_read_crlf_file_shows_plain_lines(ws):
    assert read_file("poems/crlf.md")["content"] == "first\nsecond\nthird"


@pytest.mark.parametrize("bad", ESCAPES + ["poems/missing.md", "poems"])
def test_read_file_errors(ws, bad):
    with pytest.raises(WorkspaceError):
        read_file(bad)


def test_read_start_past_end(ws):
    with pytest.raises(WorkspaceError, match="past the end"):
        read_file("poems/a.md", start_line=99)


@pytest.mark.parametrize("kwargs", [{"start_line": 0}, {"max_lines": 0}, {"max_lines": 501}])
def test_read_bad_numbers(ws, kwargs):
    with pytest.raises(WorkspaceError):
        read_file("poems/a.md", **kwargs)


def test_read_too_large(ws, monkeypatch):
    monkeypatch.setattr(config, "MAX_FILE_BYTES", 10)
    with pytest.raises(WorkspaceError, match="larger than"):
        read_file("poems/a.md")


def test_read_binary_file(ws):
    (ws / "locked.bin").write_bytes(b"\xff\xfe\x00\x80")
    with pytest.raises(WorkspaceError, match="UTF-8"):
        read_file("locked.bin")


def test_read_git_blocked_even_if_it_exists(ws):
    with pytest.raises(SandboxError):
        read_file(".git/config")


def test_read_symlink_escape_blocked(ws, outside, dir_link):
    dir_link(ws / "poems" / "link", outside)
    with pytest.raises(SandboxError):
        read_file("poems/link/secret.txt")


# ---------- write_file ----------

def test_write_creates_file(ws):
    r = write_file("feedback/review1.md", "Notes\n")
    assert r["created"] is True and r["bytes"] == 6
    assert (ws / "feedback" / "review1.md").read_text(encoding="utf-8") == "Notes\n"
    assert r["version"] == read_file("feedback/review1.md")["version"]


def test_write_creates_missing_subfolder_inside_zone(ws):
    write_file("notes/themes/water.md", "water")
    assert (ws / "notes" / "themes" / "water.md").exists()


def test_write_replaces_file_and_leaves_no_temp_file(ws):
    r = write_file("poems/a.md", "new")
    assert r["created"] is False
    assert (ws / "poems" / "a.md").read_text(encoding="utf-8") == "new"
    assert not list((ws / "poems").glob(".*.tmp"))


def test_write_handoff_file_allowed(ws):
    write_file("PROJECT_STATE.md", "# new state\n")
    assert (ws / "PROJECT_STATE.md").read_text(encoding="utf-8") == "# new state\n"


def test_write_keeps_unicode_and_newlines_exactly(ws):
    text = "caf\u00e9\nline\n"
    write_file("poems/u.md", text)
    assert (ws / "poems" / "u.md").read_bytes() == text.encode("utf-8")


@pytest.mark.parametrize("bad", ["locked.md", "trash/x.md", "newroot.md", "poems/x.py", "poems/x", "poems"])
def test_write_outside_zone_or_wrong_type_fails(ws, bad):
    with pytest.raises(SandboxError):
        write_file(bad, "x")


@pytest.mark.parametrize("bad", ESCAPES)
def test_write_path_escapes_fail(ws, bad):
    with pytest.raises(SandboxError):
        write_file(bad, "x")


def test_write_symlink_escape_fails(ws, outside, dir_link):
    dir_link(ws / "poems" / "link", outside)
    with pytest.raises(SandboxError):
        write_file("poems/link/evil.md", "x")
    assert not (outside / "evil.md").exists()


def test_write_too_large_fails_and_changes_nothing(ws, monkeypatch):
    monkeypatch.setattr(config, "MAX_FILE_BYTES", 10)
    with pytest.raises(WorkspaceError, match="limit"):
        write_file("poems/a.md", "x" * 11)
    assert "Lantern" in (ws / "poems" / "a.md").read_text(encoding="utf-8")


def test_write_exactly_at_limit_ok(ws, monkeypatch):
    monkeypatch.setattr(config, "MAX_FILE_BYTES", 10)
    write_file("poems/ten.md", "x" * 10)


def test_write_if_version_matches(ws):
    v = read_file("poems/a.md")["version"]
    assert write_file("poems/a.md", "ok", if_version=v)["created"] is False


def test_write_if_version_mismatch_reports_current_version(ws):
    v = read_file("poems/a.md")["version"]
    (ws / "poems" / "a.md").write_text("someone else edited", encoding="utf-8")
    current = read_file("poems/a.md")["version"]
    with pytest.raises(WorkspaceError, match=current):
        write_file("poems/a.md", "mine", if_version=v)
    assert (ws / "poems" / "a.md").read_text(encoding="utf-8") == "someone else edited"


def test_write_if_version_on_missing_file_fails(ws):
    with pytest.raises(WorkspaceError, match="does not exist"):
        write_file("poems/nope.md", "x", if_version="abc")


def test_write_onto_a_folder_fails(ws):
    (ws / "poems" / "folder.md").mkdir()
    with pytest.raises(WorkspaceError):
        write_file("poems/folder.md", "x")


# ---------- str_replace ----------

def test_replace_one_occurrence(ws):
    r = str_replace("poems/a.md", "Lantern light", "Candle light")
    assert r["replaced_at_line"] == 2
    assert (ws / "poems" / "a.md").read_text(encoding="utf-8") == "# A\nCandle light\nsecond line\n"


def test_replace_with_empty_string_deletes_text(ws):
    str_replace("poems/unique.txt", "two\n", "")
    assert (ws / "poems" / "unique.txt").read_text(encoding="utf-8") == "one\nthree\n"


def test_replace_not_found_fails(ws):
    with pytest.raises(WorkspaceError, match="not found"):
        str_replace("poems/a.md", "absent text", "x")


def test_replace_multiple_matches_fails_and_changes_nothing(ws):
    before = (ws / "poems" / "b.md").read_text(encoding="utf-8")
    with pytest.raises(WorkspaceError, match=r"\d+ times"):
        str_replace("poems/b.md", "a", "x")
    assert (ws / "poems" / "b.md").read_text(encoding="utf-8") == before


def test_replace_is_case_sensitive(ws):
    str_replace("poems/b.md", "LANTERN", "lamp")
    assert "the lantern again" in (ws / "poems" / "b.md").read_text(encoding="utf-8")


def test_replace_empty_old_str_fails(ws):
    with pytest.raises(WorkspaceError, match="empty"):
        str_replace("poems/a.md", "", "x")


def test_replace_multiline_on_crlf_file_keeps_crlf(ws):
    str_replace("poems/crlf.md", "first\nsecond", "uno\ndos")
    assert (ws / "poems" / "crlf.md").read_bytes() == b"uno\r\ndos\r\nthird\r\n"


@pytest.mark.parametrize("bad", ["locked.md", "trash/x.md", "poems/missing.md", "poems", "poems/x.py"] + ESCAPES)
def test_replace_errors(ws, bad):
    with pytest.raises(WorkspaceError):
        str_replace(bad, "a", "b")


def test_replace_that_grows_past_limit_fails(ws, monkeypatch):
    monkeypatch.setattr(config, "MAX_FILE_BYTES", 40)
    with pytest.raises(WorkspaceError, match="limit"):
        str_replace("poems/a.md", "second line", "y" * 50)


# ---------- delete_file ----------

def test_delete_moves_to_trash_with_timestamp(ws):
    r = delete_file("poems/a.md")
    assert not (ws / "poems" / "a.md").exists()
    assert r["moved_to"].startswith("trash/") and r["moved_to"].endswith("_poems__a.md")
    assert (ws / r["moved_to"]).read_text(encoding="utf-8").startswith("# A")


def test_delete_same_name_twice_does_not_collide(ws):
    first = delete_file("poems/a.md")["moved_to"]
    (ws / "poems" / "a.md").write_text("again", encoding="utf-8")
    second = delete_file("poems/a.md")["moved_to"]
    assert first != second and (ws / first).exists() and (ws / second).exists()


@pytest.mark.parametrize("name", ["PROJECT_STATE.md", "PLAN_LOG.md", "CHECKPOINTS.md", "DECISIONS.md"])
def test_delete_handoff_files_refused(ws, name):
    with pytest.raises(WorkspaceError, match="handoff"):
        delete_file(name)
    assert (ws / name).exists()


@pytest.mark.parametrize("bad", ["locked.md", "trash/x.md", "poems/missing.md", "poems"] + ESCAPES)
def test_delete_errors(ws, bad):
    with pytest.raises(WorkspaceError):
        delete_file(bad)


def test_delete_symlink_escape_fails(ws, outside, dir_link):
    dir_link(ws / "poems" / "link", outside)
    with pytest.raises(SandboxError):
        delete_file("poems/link/secret.txt")
    assert (outside / "secret.txt").exists()


# ---------- search_poems ----------

def test_search_finds_lines_case_insensitive(ws):
    r = search_poems("lantern")
    assert r["truncated"] is False
    assert r["matches"] == [
        {"file": "poems/a.md", "line": 2, "text": "Lantern light"},
        {"file": "poems/b.md", "line": 2, "text": "the lantern again"},
        {"file": "poems/b.md", "line": 3, "text": "LANTERN shouts"},
    ]


def test_search_no_matches(ws):
    assert search_poems("zzz")["matches"] == []


def test_search_max_results_truncates(ws):
    r = search_poems("lantern", max_results=2)
    assert len(r["matches"]) == 2 and r["truncated"] is True


def test_search_exact_count_is_not_truncated(ws):
    assert search_poems("lantern", max_results=3)["truncated"] is False


def test_search_other_folder_and_subfolders(ws):
    (ws / "notes" / "deep").mkdir()
    (ws / "notes" / "deep" / "n.md").write_text("a lantern note", encoding="utf-8")
    assert search_poems("lantern", folder="notes")["matches"][0]["file"] == "notes/deep/n.md"


def test_search_cuts_long_lines(ws):
    (ws / "poems" / "long.md").write_text("needle " + "x" * 500, encoding="utf-8")
    assert len(search_poems("needle")["matches"][0]["text"]) == 200


def test_search_skips_non_text_and_oversize_files(ws, monkeypatch):
    (ws / "poems" / "x.py").write_text("lantern", encoding="utf-8")
    (ws / "poems" / "bin.md").write_bytes(b"\xff\xfe lantern")
    assert {m["file"] for m in search_poems("lantern")["matches"]} == {"poems/a.md", "poems/b.md"}
    monkeypatch.setattr(config, "MAX_FILE_BYTES", 5)
    assert search_poems("lantern")["matches"] == []


def test_search_never_looks_in_git(ws):
    (ws / ".git" / "note.md").write_text("lantern", encoding="utf-8")
    assert all(not m["file"].startswith(".git") for m in search_poems("lantern", folder=".")["matches"])


@pytest.mark.parametrize("query", ["", "   ", "x" * 201])
def test_search_bad_query(ws, query):
    with pytest.raises(WorkspaceError):
        search_poems(query)


@pytest.mark.parametrize("bad", ESCAPES + ["missing", "locked.md"])
def test_search_folder_errors(ws, bad):
    with pytest.raises(WorkspaceError):
        search_poems("lantern", folder=bad)


def test_search_bad_max_results(ws):
    with pytest.raises(WorkspaceError):
        search_poems("lantern", max_results=0)


def test_search_does_not_follow_symlink_out(ws, outside, dir_link):
    (outside / "leak.md").write_text("lantern secret", encoding="utf-8")
    dir_link(ws / "poems" / "link", outside)
    assert all("leak" not in m["file"] for m in search_poems("lantern")["matches"])


# ---------- through the real MCP server layer ----------

def test_server_registers_the_six_tools_with_descriptions():
    import server

    tools = asyncio.run(server.mcp.list_tools())
    assert sorted(t.name for t in tools) == [
        "delete_file", "list_files", "read_file", "search_poems", "str_replace", "write_file",
    ]
    assert all(len(t.description) > 80 for t in tools)


def test_server_rejects_bad_schema_input(ws):
    import server

    with pytest.raises(Exception):
        asyncio.run(server.mcp.call_tool("read_file", {"path": "poems/a.md", "max_lines": 0}))
    with pytest.raises(Exception):
        asyncio.run(server.mcp.call_tool("str_replace", {"path": "poems/a.md", "old_str": "", "new_str": "x"}))


def test_server_reports_tool_failure_as_error_without_traceback(ws):
    import server

    with pytest.raises(Exception) as err:
        asyncio.run(server.mcp.call_tool("read_file", {"path": "../x"}))
    assert "escapes the workspace root" in str(err.value)
    assert "Traceback" not in str(err.value)
