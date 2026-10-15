import asyncio
import inspect
import json

import pytest

from poetry_lab import config, logging_utils
from poetry_lab.tools import files

SECRET_LINE = "the moth remembers the lantern"


def read_log(log_dir):
    lines = (log_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]  # every line must be valid JSON


def test_successful_call_is_logged(ws, log_dir):
    logging_utils.logged(files.list_files)("poems")
    (entry,) = read_log(log_dir)
    assert entry["tool"] == "list_files" and entry["args"] == {"folder": "poems"}
    assert entry["ok"] is True and entry["error"] is None
    assert isinstance(entry["ms"], int) and entry["time"].endswith("Z")


def test_failed_call_is_logged_and_still_raises(ws, log_dir):
    with pytest.raises(Exception, match="escapes"):
        logging_utils.logged(files.read_file)("../x")
    (entry,) = read_log(log_dir)
    assert entry["ok"] is False and "escapes the workspace root" in entry["error"]
    assert "Traceback" not in entry["error"]


def test_poem_text_is_never_logged(ws, log_dir):
    logging_utils.logged(files.write_file)("poems/new.md", SECRET_LINE)
    logging_utils.logged(files.str_replace)("poems/new.md", SECRET_LINE, "another private line")
    raw = (log_dir / "calls.jsonl").read_text(encoding="utf-8")
    assert SECRET_LINE not in raw and "another private line" not in raw
    first, second = read_log(log_dir)
    assert first["args"]["content"] == f"<{len(SECRET_LINE)} chars>"
    assert second["args"]["old_str"] == f"<{len(SECRET_LINE)} chars>"
    assert second["args"]["new_str"] == "<20 chars>"


def test_long_arguments_are_cut(ws, log_dir):
    from poetry_lab.tools.search import search_poems

    logging_utils.logged(search_poems)("x" * 150)
    (entry,) = read_log(log_dir)
    assert len(entry["args"]["query"]) == 83 and entry["args"]["query"].endswith("...")


def test_positional_and_keyword_arguments_both_logged(ws, log_dir):
    wrapped = logging_utils.logged(files.read_file)
    wrapped("poems/a.md", 1, max_lines=2)
    (entry,) = read_log(log_dir)
    assert entry["args"] == {"path": "poems/a.md", "start_line": 1, "max_lines": 2}


def test_each_call_appends_one_line(ws, log_dir):
    wrapped = logging_utils.logged(files.list_files)
    for _ in range(4):
        wrapped()
    assert len(read_log(log_dir)) == 4


def test_wrapper_keeps_the_signature_and_name():
    wrapped = logging_utils.logged(files.read_file)
    assert wrapped.__name__ == "read_file"
    assert str(inspect.signature(wrapped)) == str(inspect.signature(files.read_file))


def test_log_failure_never_breaks_the_tool(ws, tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("i am a file", encoding="utf-8")
    monkeypatch.setattr(config, "LOG_DIR", blocker / "logs")  # cannot be created
    assert logging_utils.logged(files.list_files)(".")  # tool still answers
    assert "call log write failed" in capsys.readouterr().err


def test_log_inside_the_workspace_is_refused(ws, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", ws / "logs")
    with pytest.raises(RuntimeError, match="outside the workspace"):
        logging_utils.verify_log_location()
    logging_utils.logged(files.list_files)(".")  # tool works, but nothing is written inside
    assert not (ws / "logs").exists()


def test_log_next_to_the_workspace_is_fine(ws, log_dir):
    logging_utils.verify_log_location()


def test_default_log_folder_is_outside_the_sample_workspace():
    assert (config.PROJECT_ROOT / "sample_workspace") not in config.LOG_DIR.parents
    assert config.LOG_DIR == config.PROJECT_ROOT / "logs"


def test_the_tools_cannot_read_or_write_the_log(ws, log_dir):
    logging_utils.logged(files.list_files)(".")
    for attempt in ("../logs/calls.jsonl", "logs/calls.jsonl"):
        with pytest.raises(Exception):
            files.read_file(attempt)
    with pytest.raises(Exception):
        files.write_file("../logs/calls.jsonl", "forged")


def test_calls_through_the_real_server_are_logged(ws, log_dir):
    import server

    asyncio.run(server.mcp.call_tool("list_files", {"folder": "poems"}))
    with pytest.raises(Exception):
        asyncio.run(server.mcp.call_tool("read_file", {"path": "../x"}))
    asyncio.run(server.mcp.call_tool("write_file", {"path": "notes/s.md", "content": SECRET_LINE}))
    entries = read_log(log_dir)
    assert [e["tool"] for e in entries] == ["list_files", "read_file", "write_file"]
    assert [e["ok"] for e in entries] == [True, False, True]
    assert SECRET_LINE not in (log_dir / "calls.jsonl").read_text(encoding="utf-8")


def test_git_tools_are_logged_with_the_commit_message(git_ws, log_dir):
    import server

    asyncio.run(server.mcp.call_tool("write_file", {"path": "notes/g.md", "content": "g\n"}))
    asyncio.run(server.mcp.call_tool("git_commit", {"message": "log me"}))
    entries = read_log(log_dir)
    assert entries[-1]["tool"] == "git_commit" and entries[-1]["args"] == {"message": "log me"}
