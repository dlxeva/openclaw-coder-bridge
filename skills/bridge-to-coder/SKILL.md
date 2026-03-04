# Bridge to Coder

Delegates tasks to an AI coding tool (Claude Code, Codex, OpenCode, etc.) via file queue. Polls for the reply automatically — no manual trigger needed.

## Trigger

User says things like "ask the coder", "delegate to Claude", "send this to the coder", etc.

## Flow

1. Receive instruction → reply "Submitted, waiting for response..."
2. Write task file to `inbox/` as `task-YYYYMMDD-HHmmss.md`
3. **Poll `outbox/`** every 15 seconds for `reply-{task_id}.md`
4. Wait up to 5 minutes (~20 polls); if timed out, inform the user
5. On reply found → read content → summarize and present to user

## Task Template

```markdown
from: main
to: coder

# Task

<describe the task here>
```

## Paths

- Inbox:  `~/.openclaw/workspace/skills/brain/opencode/inbox/`
- Outbox: `~/.openclaw/workspace/skills/brain/opencode/outbox/`

## Use Cases

- Architecture decisions: "A vs B — which approach?"
- Code generation: "Write a script that does X"
- Root cause analysis: "Why is this failing: [error]"
- Deep research: "Analyze and summarize [topic]"
