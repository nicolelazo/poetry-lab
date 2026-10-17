# Poetry Lab

A Python **MCP file server** that gives an AI agent safe access to a private poetry workspace. The agent acts as an *editor with memory*: it reads, searches, compares versions and leaves feedback, and it never invents poem lines. Work continues across separate agent sessions through four handoff files, not through chat memory.

Course project: CS 3A / CS 3B Elective, Week 06 Model Context Protocol, Midterms Pt 1. Requirements are in [SPEC.md](SPEC.md); the design and security reasoning is in [REPORT.md](REPORT.md).

```
agent / MCP client --HTTPS--> ngrok static domain --> 127.0.0.1:8000 (URL token check)
                                                          |
                                         FastMCP server, 9 tools, call log
                                                          |
                                    safe_path() sandbox --> WORKSPACE_ROOT (its own git repo)
```

## What you need first

| Need | Notes |
| --- | --- |
| Windows + PowerShell | Commands below are PowerShell. Linux/macOS work too with the usual path changes. |
| Python 3.11 or newer | Tested on 3.11.9. |
| Git | The workspace is its own git repo, driven through the git CLI. |
| Node.js | For pm2 and MCP Inspector. |
| ngrok account | Free account with a claimed **static domain**. The ngrok agent must be **3.20.0 or newer** (older agents are refused; run `ngrok update`). |

## Setup from scratch

1. **Get the code and make a virtual environment.**
   ```powershell
   git clone <your repo url> poetry-lab
   cd poetry-lab
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
   `mcp` is pinned below version 2 on purpose: in mcp 2.x `FastMCP` was renamed `MCPServer`, so the import used here (`from mcp.server.fastmcp import FastMCP`) only exists in 1.x.

2. **Create your `.env`** (it is git-ignored, never commit it).
   ```powershell
   copy .env.example .env
   .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Paste the printed value as `POETRY_TOKEN` and put your ngrok static domain (hostname only, no `https://`) in `NGROK_DOMAIN`. The server refuses to start if the token is missing, a placeholder, or shorter than 32 characters.

   | Variable | Meaning |
   | --- | --- |
   | `WORKSPACE_ROOT` | Folder the agent can see. `sample_workspace` for grading, a private folder outside the repo for your own poems. |
   | `POETRY_TOKEN` | Secret every request must carry in the URL as `?token=...`. |
   | `NGROK_DOMAIN` | Your static domain, e.g. `name.ngrok-free.app`. |
   | `MCP_HOST`, `MCP_PORT` | Local listen address (default `127.0.0.1:8000`). |
   | `MAX_FILE_BYTES` | Read/write size limit (default 102400). |
   | `NGROK_PATH` | Optional full path to `ngrok.exe` if it is not on your PATH. |
   | `LOG_DIR` | Optional call log folder (must be outside the workspace; default `logs`). |

3. **Run the tests** (about 70 seconds, because many tests start real git processes).
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   ```

4. **Start the server locally.**
   ```powershell
   .\.venv\Scripts\python.exe server.py
   ```
   It listens on `http://127.0.0.1:8000/mcp` and creates the workspace's own git repo on first start.

5. **Try it in MCP Inspector.** In a second terminal run `npx @modelcontextprotocol/inspector`, open the URL it prints, and choose transport **Streamable HTTP**, URL `http://127.0.0.1:8000/mcp`. Because auth is on, add `?token=<your POETRY_TOKEN>` to the URL, then Connect and open the **Tools** tab. All nine tools should be listed.

## Put it on the internet and keep it running

6. **Install pm2 and start both processes** (the Python server and the ngrok tunnel). `ecosystem.config.js` reads `NGROK_DOMAIN` from `.env` and finds `ngrok.exe` for you.
   ```powershell
   npm install -g pm2
   pm2 start ecosystem.config.js
   pm2 status
   pm2 save
   ```
   Both `poetry-lab-server` and `poetry-lab-ngrok` should show `online`. Logs go to `logs/` (git-ignored).

7. **Survive a restart.** `pm2 startup` does not work on Windows, so create a logon task that restores the saved list:
   ```powershell
   schtasks /Create /TN "PoetryLab pm2" /SC ONLOGON /TR "%APPDATA%\npm\pm2.cmd resurrect" /RL LIMITED /F
   ```
   Restart the computer, log in, wait about 30 seconds and run `pm2 status`.

8. **Check the endpoint is protected.** A request without the token must get a plain `404 Not found` (never 401):
   ```powershell
   curl.exe -i -X POST https://YOUR-DOMAIN/mcp
   ```

9. **Connect a real MCP client.** With Claude Code:
   ```powershell
   claude mcp add --scope user --transport http poetry-lab "https://YOUR-DOMAIN/mcp?token=YOUR_TOKEN"
   ```
   Then open a **new** chat (a running chat does not pick up new servers). The same URL works as a claude.ai custom connector, because the secret is in the URL and the server never answers 401 or sends `WWW-Authenticate`, so no OAuth sign-in starts.

## The nine tools

| Tool | What it does |
| --- | --- |
| `list_files` | Names in a folder; folders end with `/`. |
| `read_file` | A slice of a file (default 200 lines) plus total lines and a content `version` hash. |
| `write_file` | Create or replace a file in a write zone; optional `if_version` refuses stale writes. |
| `str_replace` | Replace exactly one occurrence of a string; fails on zero or several matches. |
| `delete_file` | Move a file to `trash/` with a timestamp. Handoff files cannot be deleted. |
| `search_poems` | Case-insensitive search; returns file, line number and matching line only. |
| `compare_versions` | Capped git diff of one file between two commits. |
| `git_commit` | Commit all workspace changes; returns the short hash. |
| `git_log` | Recent commits (hash, date, message), optionally for one file. |

Write zones are `poems/`, `notes/`, `feedback/` and the four handoff files at the workspace root, `.md`/`.txt` only, 100 KB max. `PLAN_LOG.md`, `CHECKPOINTS.md` and `DECISIONS.md` are append-only.

## The handoff protocol

Every session starts by reading `PROJECT_STATE.md` and `DECISIONS.md`, and ends by updating `PLAN_LOG.md` (what was planned, done, left), `CHECKPOINTS.md` (commit hash and why the state is consistent) and `PROJECT_STATE.md` (current truth). A real task run across two separate agent sessions (the second with no memory of the first) is saved in [transcripts/](transcripts/): the readable tool-call transcripts `session1.md` and `session2.md`, and `evidence/` with the final handoff files and the server's call log (`calls.jsonl`, one JSON line per tool call).

## Project layout

```
server.py                 entry point: FastMCP, tool registration, auth wrapper, uvicorn
ecosystem.config.js       pm2 config for the server and ngrok (no secrets in it)
package.json              marks the folder as CommonJS for Node (no dependencies)
poetry_lab/
  config.py               reads .env
  sandbox.py              safe_path(), write zones, write guards, workspace lock
  auth.py                 URL token middleware
  logging_utils.py        call logger (logs/calls.jsonl)
  tools/files.py          list_files, read_file, write_file, str_replace, delete_file
  tools/search.py         search_poems
  tools/gitlite.py        compare_versions, git_commit, git_log, workspace repo setup
tests/                    pytest: sandbox, tools, git, auth, logging
sample_workspace/         fake poems and the four handoff files (committed for graders)
transcripts/              tool-call transcripts of the two-session task, and evidence
logs/                     call log (git-ignored, outside the workspace)
```

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `ModuleNotFoundError: mcp.server.fastmcp` | mcp 2.x installed. Reinstall with `pip install -r requirements.txt` (pins `<2`). |
| pm2 shows ngrok in `waiting restart`; log says agent version too old | Run `ngrok update` (needs 3.20.0+), then `pm2 restart poetry-lab-ngrok`. |
| `ecosystem.config.js` loads as an empty object | A parent folder has a `package.json` with `"type": "module"`. The `package.json` in this repo overrides it; keep it. |
| Server will not start: `Refusing to start` | Fix `POETRY_TOKEN` in `.env` (32+ random characters). |
| Port 8000 already in use | An old `python server.py` is still running; stop it, then `pm2 restart poetry-lab-server`. |
| New MCP server not visible in a chat | Chats load servers when they start. Open a new chat. |
| One request fails with `ERR_NGROK_3004` / "ngrok gateway error" | The free tunnel occasionally drops a request before it reaches your server. Retry once; if it keeps failing check `pm2 status` and `pm2 logs poetry-lab-ngrok`. |
| A console window titled `...\.venv\Scripts\python.exe` appears at logon | Windows Terminal opens a window for the server's console. `ecosystem.config.js` therefore starts the server with `pythonw.exe` (no console). After pulling that change run `pm2 delete poetry-lab-server`, `pm2 start ecosystem.config.js --only poetry-lab-server`, then `pm2 save`. |
| `421 Invalid Host header` | `NGROK_DOMAIN` in `.env` does not match the domain you are calling; fix it and restart the server. |
