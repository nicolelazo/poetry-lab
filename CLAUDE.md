# CLAUDE.md: Poetry Lab

**Read [SPEC.md](SPEC.md) first. It is the source of truth.** If anything conflicts (SPEC vs. slides vs. these rules vs. what the user asks), tell the user and ask before deciding.

## Project summary

Poetry Lab is a Python MCP file server (official MCP Python SDK, `FastMCP`, Streamable HTTP) for the Week 6 MCP midterm. It gives an AI agent safe, sandboxed access to a private poetry workspace so the agent can act as an editor with memory: it reads, searches, compares versions and leaves feedback, and it never invents poem lines. The project is proven by running one real task across 2 or more separate agent sessions that continue each other through the handoff files (PROJECT_STATE, PLAN_LOG, CHECKPOINTS, DECISIONS), not through chat memory.

## How we work (rules that persist across sessions)

1. **One milestone at a time** (M1 to M5, see SPEC.md section 9). Stop at the end of each one and wait for the user to say "next".
2. **Plan first.** Before coding, state the plan in a few short lines, then proceed unless something is unclear.
3. **Explain every file.** After each file you create, explain in 2 to 4 simple sentences what it does. The user must be able to explain every file.
4. **Commit at the end of each milestone** with a clear message. No giant commits.
5. **Never print or commit secrets.** Secrets live only in `.env` (gitignored). Keep `.env.example` with placeholders.
6. **Ask before installing** anything not listed in SPEC.md.
7. **Run the tests after every change** and show the output.
8. **Stay inside this project folder.** Use fake sample poems only, never real ones.

## Status

M1 to M5 are complete (see `git log`). The task run across two agent sessions is recorded in `transcripts/`; README and REPORT are written. Remaining work is the owner's: read the class AI-use policy (REPORT section 8) and publish the repo.

## Project facts worth remembering

* Windows, Python 3.11.9, virtual environment in `.venv/` (run tools with `.\.venv\Scripts\python.exe`).
* `mcp` is pinned below 2 (`mcp>=1.2,<2`). In mcp 2.x `FastMCP` was renamed `MCPServer` and SPEC's import `from mcp.server.fastmcp import FastMCP` breaks. The user chose to pin.
* Server runs under pm2 (`poetry-lab-server`, `poetry-lab-ngrok`) behind a bearer token; restart it with `pm2 restart poetry-lab-server` after code changes. The MCP server is registered in the user's Claude Code config as `poetry-lab` (user scope).
* The workspace is its own git repo (auto-created by `ensure_workspace_repo()`; `sample_workspace/.git/` is ignored by the code repo). Git runs only as fixed argument lists pinned with `GIT_DIR`/`GIT_WORK_TREE`.
* Write guards: PLAN_LOG, CHECKPOINTS and DECISIONS are append-only; blank and NUL content is refused. Every tool call is logged to `logs/calls.jsonl` (no poem text).
* PowerShell 5.1 `Set-Content -Encoding utf8` adds a BOM; use the Edit/Write tools for source files instead.
* Git commit messages end with the `Co-Authored-By` line given by the Claude Code attribution reminder.
