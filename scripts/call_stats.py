"""Summarise logs/calls.jsonl: how many tool calls, which tools, how many failed.

Usage:  .venv\\Scripts\\python.exe scripts\\call_stats.py [path-to-calls.jsonl]
Efficiency is judged from logs, so this gives the numbers to quote in the report.
"""

import json
import sys
from collections import Counter
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / "logs" / "calls.jsonl"


def main(path: Path) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    errors = [r for r in rows if not r["ok"]]
    print(f"{len(rows)} tool calls, {len(errors)} errors, {sum(r['ms'] for r in rows)} ms total tool time")
    for tool, count in Counter(r["tool"] for r in rows).most_common():
        print(f"  {tool:<17} {count}")
    for r in errors:
        print(f"  error in {r['tool']}: {r['error']}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT)
