# openclaw-coder-bridge

A background daemon that lets your [OpenClaw](https://openclaw.ai/) AI agent delegate tasks to any AI coding tool (Claude Code, Codex, OpenCode, etc.) — asynchronously, with zero token polling and automatic Telegram notifications when done.

## How It Works

Your OpenClaw agent drops a task file into `inbox/`. The bridge picks it up, runs your coding AI in non-interactive mode, writes the result to `outbox/`, and pings you on Telegram.

```
OpenClaw Agent
    │  writes task-*.md
    ▼
inbox/  ←── bridge watches every 2s
    │
    ▼
coder-bridge.py  ──►  bash -c "claude -p --dangerously-skip-permissions"
                              (swap in codex / opencode / any CLI tool)
    │
    ▼
outbox/reply-{task_id}.md  +  Telegram notification
    │
    ▼
OpenClaw Agent reads result
```

**Key properties:**
- Agent token cost during coding = 0 (agent is not waiting, bridge handles it)
- Single instance guaranteed via PID lock file
- Failed tasks are archived, never retried infinitely

## Requirements

- [OpenClaw](https://openclaw.ai/) installed and configured
- A CLI-based AI coding tool:
  - [Claude Code](https://github.com/anthropics/claude-code): `npm install -g @anthropic-ai/claude-code`
  - Or Codex, OpenCode, etc.
- Python 3.8+
- Windows (Linux/Mac support planned)
- [Git for Windows](https://git-scm.com/download/win) — required if using Claude Code (its wrapper script needs bash)

## Installation

### 1. Place the bridge script

Copy `coder-bridge.py` to your preferred location. Recommended:

```
%USERPROFILE%\.openclaw\workspace\skills\brain\opencode\coder-bridge.py
```

`inbox/`, `outbox/`, and `archive/` subdirectories are created automatically on first run.

### 2. Configure autostart (Windows)

Edit `setup/start-bridge.vbs` with your credentials:

```vbs
oShell.Environment("Process")("TELEGRAM_BOT_TOKEN") = "YOUR_BOT_TOKEN"
oShell.Environment("Process")("TELEGRAM_CHAT_ID") = "YOUR_CHAT_ID"
```

Create a shortcut in your Windows Startup folder:

| Field | Value |
|-------|-------|
| Target | `C:\Windows\System32\wscript.exe` |
| Arguments | `%USERPROFILE%\.openclaw\scripts\start-bridge.vbs` |
| Location | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` |

> **Why target `wscript.exe` instead of the `.vbs` directly?**
> Windows shortcuts corrupt non-ASCII characters (e.g. usernames with CJK characters) in hardcoded paths.
> Pointing to `wscript.exe` and using `%USERPROFILE%` in Arguments lets Windows expand at runtime, bypassing the bug.

### 3. Add the OpenClaw Skill

Copy `skills/bridge-to-coder/SKILL.md` to your OpenClaw skills directory:

```
%USERPROFILE%\.openclaw\workspace\skills\bridge-to-coder\SKILL.md
```

Restart OpenClaw. Your agent can now say things like "ask the coder: [your question]" and will write the task and poll for the reply automatically.

## Task File Format

Create a `task-*.md` file (name **must** start with `task-`) in `inbox/`:

```markdown
from: main
to: coder

# Task title

Your task description. For example:
- "Analyze the performance bottleneck in this function: ..."
- "Compare approach A vs B for implementing feature X"
- "Write a Python script that does Y"
- "Diagnose this error: [paste stack trace]"
```

The bridge processes it within 2 seconds and writes `outbox/reply-{task_id}.md` when done.

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Your OpenClaw Telegram bot token | — (notifications disabled if unset) |
| `TELEGRAM_CHAT_ID` | Telegram chat ID to receive notifications | — |
| `BASH_EXE` | Path to `bash.exe` | Auto-detected from Git for Windows |
| `CODER_TIMEOUT` | Max seconds to wait for the coding AI per task | `600` |

## Switching to a Different Coding AI

The bridge calls `claude -p --dangerously-skip-permissions` by default. To use a different tool, modify the command in `run_coder()` inside `coder-bridge.py`:

```python
# Example: use Codex instead
result = subprocess.run(
    ["codex", "--non-interactive"],
    input=prompt,
    ...
)
```

## Troubleshooting

### The coding AI hangs and never returns

**Cause:** The CLI tool is waiting for interactive confirmation (file access permissions, tool use, etc.)

**Fix:** Claude Code requires `--dangerously-skip-permissions` to run non-interactively. For other tools, find the equivalent "auto-approve" flag.

### Duplicate processing (WinError 2)

**Cause:** Multiple bridge instances running simultaneously (e.g. two startup entries).

**Fix:** The bridge writes `bridge.pid` on startup and exits if another instance is already running.
If stuck: `taskkill /F /IM python.exe`, delete `bridge.pid`, restart.

### Path corruption with non-ASCII usernames (Windows)

**Cause:** Windows default GBK/ANSI encoding conflicts with UTF-8 expected by Git Bash and Node.js.

**Fix:** Control Panel → Region → Administrative → Change system locale → enable **"Beta: Use Unicode UTF-8"** → reboot.

### Git Bash not found

Install [Git for Windows](https://git-scm.com/download/win), or override the path:

```
set BASH_EXE=C:\your\path\Git\usr\bin\bash.exe
```

### Why does Claude Code need Git Bash?

Claude Code's npm wrapper (`claude`) is a bash script that depends on Unix tools (`sed`, `dirname`, `uname`). On Windows it must be invoked through Git Bash — calling it directly from `cmd.exe` or PowerShell fails.

## License

MIT
