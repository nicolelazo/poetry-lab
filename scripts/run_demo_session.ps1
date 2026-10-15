# Run one demo session as a fresh, memory-less Claude Code session that can use only the
# poetry-lab MCP tools (the server must be running and registered with `claude mcp add`).
#
#   powershell -File scripts\run_demo_session.ps1 -Session 1
#   powershell -File scripts\run_demo_session.ps1 -Session 2
#
# The session starts in an empty temp folder so it cannot see this project's CLAUDE.md or files.
# The raw recording and a readable transcript are saved in that temp folder, not in the repo.
param(
    [Parameter(Mandatory = $true)][ValidateSet("1", "2")][string]$Session
)

$repo = Split-Path $PSScriptRoot -Parent
$prompt = Get-Content (Join-Path $PSScriptRoot "demo_prompts\session$Session.txt") -Raw
$work = Join-Path $env:TEMP "poetry-lab-demo"
New-Item -ItemType Directory $work -Force | Out-Null
$raw = Join-Path $work "session$Session.raw.jsonl"
$md = Join-Path $work "session$Session.md"

Push-Location $work
try {
    $prompt | claude -p --output-format stream-json --verbose --no-session-persistence `
        --allowedTools "mcp__poetry-lab" `
        --disallowedTools "Bash" "PowerShell" "Read" "Write" "Edit" "Glob" "Grep" "WebFetch" "WebSearch" "Agent" "NotebookEdit" `
        2>&1 | Out-File -Encoding utf8 $raw
}
finally {
    Pop-Location
}

& (Join-Path $repo ".venv\Scripts\python.exe") (Join-Path $repo "scripts\make_transcript.py") $raw $md "Demo session $Session"
Write-Host "Readable transcript: $md"
Write-Host "Tool-call stats:     .venv\Scripts\python.exe scripts\call_stats.py"
