"""Turn a Claude Code stream-json session recording into a readable Markdown transcript.

Usage:  python scripts/make_transcript.py raw.jsonl out.md "Session title"
Prints a one-line summary (tool calls, errors) that is also written at the top of the file.
"""

import json
import sys
from pathlib import Path

MAX_RESULT_CHARS = 900


def short_name(name: str) -> str:
    return name.split("__")[-1]


def result_text(content) -> str:
    if isinstance(content, list):
        content = " ".join(block.get("text", "") for block in content if isinstance(block, dict))
    text = str(content).strip()
    return text if len(text) <= MAX_RESULT_CHARS else text[:MAX_RESULT_CHARS] + f"\n... [{len(text) - MAX_RESULT_CHARS} more characters cut]"


def main(raw_path: str, out_path: str, title: str) -> None:
    events = [json.loads(line) for line in Path(raw_path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    body, calls, errors, pending = [], 0, 0, {}

    for event in events:
        kind = event.get("type")
        if kind == "user" and isinstance(event.get("message", {}).get("content"), list):
            for block in event["message"]["content"]:
                if block.get("type") == "tool_result":
                    is_error = bool(block.get("is_error"))
                    errors += is_error
                    name = pending.get(block.get("tool_use_id"), "?")
                    body.append(f"**Result** (`{name}`{', ERROR' if is_error else ''}):\n```\n{result_text(block.get('content'))}\n```\n")
        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text" and block["text"].strip():
                    body.append(f"**Agent:** {block['text'].strip()}\n")
                elif block.get("type") == "tool_use":
                    calls += 1
                    pending[block["id"]] = short_name(block["name"])
                    body.append(f"**Call {calls}:** `{short_name(block['name'])}`\n```json\n{json.dumps(block['input'], ensure_ascii=False, indent=2)}\n```\n")

    final = next((e for e in reversed(events) if e.get("type") == "result"), {})
    summary = (
        f"{calls} tool calls, {errors} errors, {final.get('num_turns', '?')} turns, "
        f"{round(final.get('duration_ms', 0) / 1000)} s"
    )
    header = f"# {title}\n\n**Summary:** {summary}\n\n---\n\n"
    Path(out_path).write_text(header + "\n".join(body), encoding="utf-8")
    print(f"{title}: {summary}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
