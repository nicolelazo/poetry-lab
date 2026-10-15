# 5-minute live demo: Poetry Lab

Goal: show one real task finished across **two separate agent sessions** that share nothing except files, and explain the design choices. Total about 5 minutes; the two agent runs take about 25 seconds each.

## Before you go on (2 minutes, off the clock)

1. `pm2 status` shows `poetry-lab-server` and `poetry-lab-ngrok` both `online`.
2. `curl.exe -i -X POST https://YOUR-DOMAIN/mcp` prints `401`.
3. Reset the workspace: `.\.venv\Scripts\python.exe scripts\reset_demo.py`
4. Open on screen: this file, `sample_workspace/`, a terminal in the project folder, and `transcripts/session1.md` (the saved run, as a fallback).
5. Know your two commands (below). If you would rather show a chat than a terminal, open a **new** Claude Code chat in an **empty folder** (not in this project, so it cannot read `CLAUDE.md`) and paste the prompts from `scripts/demo_prompts/`.

## Timeline

| Time | Say | Show |
| --- | --- | --- |
| 0:00 | "An MCP file server that lets an AI work as a poetry editor with memory. The memory is four files, not the chat." | The architecture diagram in `README.md`. |
| 0:30 | "It is live on the internet, but locked: no token means 401. It is kept alive by pm2 and survives a reboot." | `pm2 status`, then the `curl.exe` 401. |
| 1:00 | "Session 1 is a fresh agent with no memory. It must read the state, search before it reads, write feedback, commit, and hand off." | Run `powershell -File scripts\run_demo_session.ps1 -Session 1` and narrate the summary line: about 15 to 17 calls, 0 errors. Open the transcript and point at: reads `PROJECT_STATE` first, `search_poems` before any poem read, one `write_file` to `feedback/`, then `git_commit`. |
| 2:00 | "Rule 2 in DECISIONS: the agent may only suggest. I decide." | Open `sample_workspace/feedback/` note. Say which single change you approve (the default in the prompt is to cut "slow and" from `harbor-lantern` line 4). |
| 2:30 | "Session 2 is a different agent that has never seen Session 1. It finds the note through `PROJECT_STATE`." | Run `powershell -File scripts\run_demo_session.ps1 -Session 2`. Point at: `compare_versions`, then one `str_replace`, then a new line in `DECISIONS.md`. |
| 3:30 | "Proof, from files not claims." | `git -C sample_workspace log --oneline` (3 commits), `git -C sample_workspace diff HEAD~1 HEAD -- poems/harbor-lantern.md` (exactly the approved line), and `PLAN_LOG.md` / `CHECKPOINTS.md`. |
| 4:00 | "Efficiency is judged from logs." | `.\.venv\Scripts\python.exe scripts\call_stats.py`: about 27 to 30 calls, 0 errors. |
| 4:20 | "Security: the agent cannot escape or destroy anything." | Ask any client to `read_file ../x` or `delete_file DECISIONS.md` and show the clean `isError` message. |
| 4:45 | "Tradeoffs: one shared token, free tunnel, no rate limit. Next step is per-client tokens." | `REPORT.md` section 4. Stop. |

## Run the two sessions

```powershell
powershell -File scripts\run_demo_session.ps1 -Session 1
powershell -File scripts\run_demo_session.ps1 -Session 2
```

Each starts a fresh Claude session in an empty temp folder that can use only the `poetry-lab` tools. The readable transcript path is printed at the end.

## If something goes wrong

| Problem | Do this |
| --- | --- |
| "ngrok gateway error" (`ERR_NGROK_3004`) on one call | It is the free tunnel dropping one request. Retry once (the agents retry on their own). If it persists, say so and open the saved `transcripts/session1.md` and `session2.md`. |
| Server not answering | `pm2 status`, then `pm2 restart poetry-lab-server poetry-lab-ngrok`. |
| Workspace in a messy state | `scripts\reset_demo.py`, then start again from Session 1. |
| Session says it cannot use the tools | The server is not registered for that user: `claude mcp list` should show `poetry-lab` connected. |
| Out of time | Skip the live Session 2 and walk through `transcripts/session2.md` and `transcripts/demo_evidence/`. |

## Likely questions and short answers

* **Why Python and FastMCP?** Typed functions become tools with strict JSON schemas, so validation comes from the type hints; I pinned `mcp<2` because 2.x renamed `FastMCP`.
* **Why is each tool single purpose?** The description is the prompt the model reads; one verb per tool makes success and failure unambiguous, and gating is easy (only `delete_file` moves files, and only to `trash/`).
* **How do you stop path escapes?** `safe_path()` rejects absolute, `..`, backslash, drive and `:` paths and resolves symlinks, then checks the result is inside the root. Tests cover `../x`, `poems/../../x`, absolute, Windows style and symlink/junction.
* **What if a poem contains instructions for the agent (prompt injection)?** The prompt rules are guidance, not security. The code refuses the dangerous things anyway: no deleting handoff files, append-only logs, no writes outside the zones, everything logged.
* **How do two agents avoid overwriting each other?** One lock plus atomic writes, and `if_version` so a writer can detect a stale read. 20 simultaneous edits are tested.
* **Why is the token not in the URL?** URLs end up in logs and history. The header is better; the spec's URL fallback was not needed because my client can send headers.
* **What did the agents do badly?** Two unneeded calls in Session 1, and both left their handoff edits uncommitted because the spec order is commit then update (see `REPORT.md` section 5).
