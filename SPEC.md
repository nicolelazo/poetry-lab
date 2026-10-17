# SPEC: Poetry Lab MCP Server

Course project: CS 3A / CS 3B Elective, Week 06 Model Context Protocol, Midterms Pt 1.
Reference slides: the course deck `MCP_Week6_Presentation2.pptx.pdf`, not included in this repo (sheets 16 to 20 define the requirements and rubric).

## 1. Goal

Build and deploy my own MCP file server connector. It gives an AI agent safe access to a private poetry workspace. The agent acts as an **editor with memory**. It reads, searches, compares versions and leaves feedback. It never invents poem lines.

The project is proven by running one real task across 2 or more separate agent sessions, where each new session continues the previous one through files, not through chat memory.

## 2. Rules for Claude Code (read first)

1. Work on **one milestone at a time**. Stop at the end of each milestone and wait for me to say "next".
2. Before writing code, say in plain words what you are about to build and why.
3. After each file you create, explain in 2 to 4 simple sentences what it does. I must be able to explain every file in a live demo.
4. Make a git commit at the end of each milestone with a clear message. No giant commits.
5. Never print, log or commit secrets. The token lives only in `.env`, which is gitignored. Provide `.env.example` with placeholder values.
6. Ask before installing anything not listed in this spec.
7. Run the tests after every change and show me the result.
8. Do not touch anything outside this project folder.
9. Do not use my real poems. Use fake sample poems only.

## 3. Stack (final decisions)

| Layer | Choice |
| --- | --- |
| Language and SDK | Python 3.11 or newer, official MCP Python SDK (`from mcp.server.fastmcp import FastMCP`) |
| Validation | pydantic models or typed parameters on every tool input |
| Transport | Streamable HTTP (stdio only for quick local tests) |
| Exposure | ngrok with a static domain |
| Process manager | pm2 (runs both the Python server and ngrok) |
| Version control | git CLI, called through Python `subprocess` with fixed argument lists (never `shell=True`) |
| Testing | pytest, then MCP Inspector, then a real MCP client |
| Config | environment variables loaded from `.env` with python-dotenv |

Check the current SDK docs for exact run options before coding, since versions change.

## 4. Project layout

```
poetry-lab/
  SPEC.md
  README.md                 setup anyone can follow
  REPORT.md                 short report (stack, tool design, security tradeoffs)
  .env.example
  .gitignore                .env, .venv, workspace_private/, logs/
  ecosystem.config.js       pm2 config for server and ngrok
  requirements.txt
  server.py                 entry point, creates FastMCP, registers tools, starts server
  poetry_lab/
    config.py               reads env vars (WORKSPACE_ROOT, POETRY_TOKEN, limits)
    sandbox.py              safe_path() and write zone checks
    auth.py                 URL token middleware
    logging_utils.py        call logger
    tools/
      files.py              list_files, read_file, write_file, str_replace, delete_file
      search.py             search_poems
      gitlite.py            compare_versions, git_commit, git_log
  tests/
    test_sandbox.py
    test_tools.py
    test_auth.py
  sample_workspace/         fake poems and the four handoff files, committed for graders
  logs/                     call logs (gitignored, lives OUTSIDE the workspace)
  transcripts/              saved demo transcripts
```

`WORKSPACE_ROOT` in `.env` points to the workspace folder. For grading it points to `sample_workspace/`. For my own use it points to a private folder outside the repo.

### Workspace layout (inside WORKSPACE_ROOT)

```
poems/          one markdown file per poem
notes/          themes, recurring images, ideas
feedback/       editor notes, one file per review
trash/          deleted files are moved here
PROJECT_STATE.md
PLAN_LOG.md
CHECKPOINTS.md
DECISIONS.md
```

The workspace is its own git repo (`git init` inside it), separate from the code repo.

## 5. Sandbox rules (requirement 01)

* Every path from the agent is treated as relative to `WORKSPACE_ROOT`.
* `safe_path(rel)` joins, resolves (including symlinks), and rejects anything that is not inside the root. Absolute paths, `..` tricks, and symlink escapes must all fail.
* **Write zones.** Writes are allowed only in `poems/`, `notes/`, `feedback/`, and the four handoff files at the root. Everything else is read only.
* Maximum file size for reads and writes: 100 KB. Reject larger.
* Only `.md` and `.txt` files can be written.
* The `.git` folder is never readable or writable through tools.

## 6. Tools (requirement 02, 9 tools)

Every tool is single purpose, has a strict input schema, and has a description that says **what it does, when to use it, and how it fails**. Failures must raise clear errors so the SDK returns `isError`. Never return raw stack traces.

| Tool | Inputs | Behavior |
| --- | --- | --- |
| `list_files` | `folder` (default `.`) | Lists names in a folder. Folders end with `/`. |
| `read_file` | `path`, `start_line` (default 1), `max_lines` (default 200) | Returns the requested slice plus total line count and a content `version` (hash). Keeps output small. |
| `write_file` | `path`, `content`, `if_version` (optional) | Creates or replaces a file inside a write zone. If `if_version` is given and does not match the current file, fail and report the current version. |
| `str_replace` | `path`, `old_str`, `new_str` | Replaces exactly one occurrence. Fails if `old_str` appears zero times or more than once. |
| `delete_file` | `path` | Moves the file to `trash/` with a timestamp. Refuses to delete the four handoff files. |
| `search_poems` | `query`, `folder` (default `poems`), `max_results` (default 20) | Case insensitive text search. Returns file, line number and the matching line only. Never returns whole files. |
| `compare_versions` | `path`, `from_ref` (default `HEAD~1`), `to_ref` (default `HEAD`) | Returns the git diff of one file between two commits. Output is capped. |
| `git_commit` | `message` | Commits all workspace changes. Rejects an empty message. Returns the short commit hash. |
| `git_log` | `path` (optional), `limit` (default 10, max 50) | Lists recent commits as short hash, date and message. |

Tool descriptions are the prompt the agent reads. Write them carefully.

## 7. Security (requirement 01, rubric criterion E)

* **Auth.** Every request to the public endpoint must carry `?token=<POETRY_TOKEN>` in the URL (claude.ai connectors cannot send custom headers and start OAuth on a 401). Compare with `secrets.compare_digest`. Missing or wrong token returns a plain 404 `Not found`, never 401 and never `WWW-Authenticate`. Run uvicorn with `--no-access-log` so the URL is not logged. Note this tradeoff in the report.
* **Secrets.** `POETRY_TOKEN` and the ngrok authtoken live only in `.env`.
* **Destructive actions.** `delete_file` moves to `trash/` and never erases. Handoff files cannot be deleted.
* **Logging.** Every tool call is appended to `logs/calls.jsonl` outside the workspace so agents cannot edit it. Record time, tool name, a short summary of arguments, and success or error. Do not log full poem text.
* **Subprocess safety.** Git is called with fixed argument lists. User text goes only into arguments, never into a shell string.
* **Tests.** Path traversal tests must cover: `../x`, `poems/../../x`, an absolute path, a Windows style path, and a symlink pointing outside.
* **Threat notes for the report.** Stolen token, prompt injection through poem text, large file abuse, concurrent writes.

## 8. Handoff protocol (requirement 04)

Four files at the workspace root. Starter templates:

**PROJECT_STATE.md**: current truth. Sections: `Goal`, `Poems in progress`, `Poems done`, `Open questions`, `Next step`, `Last updated by` (session id and date). Every session reads this first and rewrites it before ending.

**PLAN_LOG.md**: append only log. One entry per session: date, session id, what was planned, what was done, what was left.

**CHECKPOINTS.md**: safe points. Entry format: date, commit hash, "state is clean and consistent because ...".

**DECISIONS.md**: rules and choices that later sessions must respect. Starter rules:
1. The agent is an editor. It never writes new lines or poems on its own.
2. The agent may suggest changes in `feedback/`. It edits a poem only when I approve that specific change.
3. Keep the style spare. Do not add explanations to poems.
4. Never rewrite a line that has been marked final.
5. Read PROJECT_STATE and DECISIONS before anything else.

## 9. Milestones (match slide 17)

**M1 Skeleton.** Project setup, virtual environment, `requirements.txt`, FastMCP server with only `list_files` and `safe_path`. Done when `list_files` answers in MCP Inspector.

**M2 Sandbox.** All file tools plus `search_poems`, write zones, size limits, clear errors, and pytest tests for path escapes and each tool. Done when all tests pass and Inspector shows every tool working.

**M3 Deploy.** Token auth, `.env` handling, ngrok static domain, pm2 `ecosystem.config.js`. Done when a real MCP client connects over HTTPS, a request without the token gets 404, and the server survives a restart of the computer.

**M4 Protocol.** Workspace git repo, `compare_versions`, `git_commit`, `git_log`, the four handoff files with templates, call logging, and bad write guards. Stretch if time allows: `if_version` locking fully tested, and a `repo_map` or tree view tool.

**M5 Prove it.** Run the demo task (section 10), save transcripts, write README and REPORT, rehearse the 5 minute live demo.

## 10. Demo task (requirement 05)

Use fake sample poems. Run in two separate fresh chats with a real MCP client.

**Session 1.** The agent reads `PROJECT_STATE.md` and `DECISIONS.md`. It uses `search_poems` for one repeated image across all poems (search first, do not open every file). It reads only the matching poems. It writes one note in `feedback/`, calls `git_commit`, then updates `PLAN_LOG.md`, `CHECKPOINTS.md` and `PROJECT_STATE.md`.

**Session 2.** A new agent has no memory. It reads `PROJECT_STATE.md`, finds the feedback note, and runs `compare_versions` on one poem. After I approve one specific change, it uses `str_replace` on that line. It records the choice in `DECISIONS.md`, commits, and updates the handoff files.

Efficiency goals (rubric criterion A): few and purposeful calls, read before write, small outputs, no repeated calls without new information, and a clear stop condition. Save both transcripts in `transcripts/`.

## 11. Deliverables and rubric reminders

* Working repository with meaningful git history (small commits, clear messages).
* README that a classmate can follow to rebuild the project from scratch.
* Tool call transcript of the demo task.
* PLAN_LOG and CHECKPOINTS files from the demo.
* REPORT.md covering: why this stack, why each tool is single purpose, security tradeoffs.
* 5 minute live demo.

Rubric weights: agent efficiency 20, agent and tool management 20, tool design 20, stack and architecture 15, security 10, documentation and demo 15.

## 12. Things the human does (not Claude Code)

* Create the ngrok account and claim the static domain.
* Generate the token and put it in `.env`.
* Connect the real MCP client to the public URL.
* Read and try to break the path escape tests.
* Run the two demo sessions and review the transcripts.
* Check class rules on AI tool use and mention it in the report if required.
