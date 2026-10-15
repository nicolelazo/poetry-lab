import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import call_stats  # noqa: E402


def test_call_stats_summarises_a_log(tmp_path, capsys):
    log = tmp_path / "calls.jsonl"
    rows = [
        {"tool": "read_file", "ok": True, "ms": 10, "error": None},
        {"tool": "read_file", "ok": False, "ms": 5, "error": "WorkspaceError: nope"},
        {"tool": "git_log", "ok": True, "ms": 1, "error": None},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    call_stats.main(log)
    out = capsys.readouterr().out
    assert "3 tool calls, 1 errors, 16 ms" in out
    assert "read_file" in out and "WorkspaceError: nope" in out


def test_saved_two_session_evidence_is_consistent():
    transcripts = ROOT / "transcripts"
    for name in ("session1.md", "session2.md"):
        summary = (transcripts / name).read_text(encoding="utf-8").split("**Summary:**")[1].splitlines()[0]
        assert "0 errors" in summary
    rows = [
        json.loads(line)
        for line in (transcripts / "evidence" / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 30 and all(r["ok"] for r in rows)
    # poem text must never be in the call log: write arguments are logged as lengths only
    for r in rows:
        if r["tool"] in ("write_file", "str_replace"):
            assert all(str(v).startswith("<") for k, v in r["args"].items() if k in ("content", "old_str", "new_str"))


def test_handoff_files_from_the_task_are_present_and_filled_in():
    evidence = ROOT / "transcripts" / "evidence"
    plan_log = (evidence / "PLAN_LOG.md").read_text(encoding="utf-8")
    checkpoints = (evidence / "CHECKPOINTS.md").read_text(encoding="utf-8")
    assert "session 1" in plan_log and "session 2" in plan_log
    assert checkpoints.count("## 2026-") == 2
