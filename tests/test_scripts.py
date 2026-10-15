import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import call_stats  # noqa: E402
import make_transcript  # noqa: E402


def write_jsonl(path, rows, bom=False):
    text = "\n".join(json.dumps(r) for r in rows) + "\n"
    path.write_text(("﻿" if bom else "") + text, encoding="utf-8")


def tool_use(call_id, name, **args):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": call_id, "name": f"mcp__poetry-lab__{name}", "input": args}]}}


def tool_result(call_id, text, error=False):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": call_id, "content": text, "is_error": error}]}}


def test_transcript_counts_calls_and_errors_and_accepts_a_bom(tmp_path, capsys):
    raw = tmp_path / "raw.jsonl"
    write_jsonl(
        raw,
        [
            tool_use("a", "read_file", path="PROJECT_STATE.md"),
            tool_result("a", "state text"),
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Trying a bad path."}]}},
            tool_use("b", "read_file", path="../x"),
            tool_result("b", "Path escapes the workspace root.", error=True),
            {"type": "result", "num_turns": 3, "duration_ms": 4000},
        ],
        bom=True,
    )
    out = tmp_path / "out.md"
    make_transcript.main(str(raw), str(out), "Test session")
    text = out.read_text(encoding="utf-8")
    assert "2 tool calls, 1 errors, 3 turns, 4 s" in text
    assert "**Call 1:** `read_file`" in text and "ERROR" in text and "Trying a bad path." in text
    assert "Test session" in capsys.readouterr().out


def test_transcript_cuts_very_long_results(tmp_path):
    raw = tmp_path / "raw.jsonl"
    write_jsonl(raw, [tool_use("a", "read_file", path="x"), tool_result("a", "y" * 5000), {"type": "result"}])
    out = tmp_path / "out.md"
    make_transcript.main(str(raw), str(out), "T")
    assert "more characters cut" in out.read_text(encoding="utf-8")


def test_saved_demo_transcripts_match_the_recorded_call_log():
    evidence = Path(__file__).resolve().parent.parent / "transcripts"
    summary = lambda name: (evidence / name).read_text(encoding="utf-8").split("**Summary:**")[1].splitlines()[0]
    assert "0 errors" in summary("session1.md") and "0 errors" in summary("session2.md")
    rows = [json.loads(l) for l in (evidence / "demo_evidence" / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 30 and all(r["ok"] for r in rows)
    assert not any("lantern" in json.dumps(r["args"]).lower() and r["tool"] in ("write_file", "str_replace") and "chars>" not in json.dumps(r["args"]) for r in rows)


def test_call_stats_summarises_a_log(tmp_path, capsys):
    log = tmp_path / "calls.jsonl"
    write_jsonl(
        log,
        [
            {"tool": "read_file", "ok": True, "ms": 10, "error": None},
            {"tool": "read_file", "ok": False, "ms": 5, "error": "WorkspaceError: nope"},
            {"tool": "git_log", "ok": True, "ms": 1, "error": None},
        ],
    )
    call_stats.main(log)
    out = capsys.readouterr().out
    assert "3 tool calls, 1 errors, 16 ms" in out
    assert "read_file" in out and "WorkspaceError: nope" in out
