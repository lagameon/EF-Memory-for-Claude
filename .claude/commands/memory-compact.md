# /memory-compact — Compact events.jsonl and Archive History

## Purpose

Compact the append-only `events.jsonl` by resolving latest-wins, removing deprecated entries, and archiving removed lines to quarterly shard files.

**This is like `git gc` for memory — it reduces file size without losing data.**

---

## When to use

- When startup shows "compact suggested (Nx waste)"
- Periodically as hygiene (monthly)
- After large batch imports or bulk deprecations
- When events.jsonl feels slow to load

---

## Input

| Format | Description |
|--------|-------------|
| `/memory-compact` | Run compaction (default) |
| `/memory-compact --stats` | Show waste statistics only |
| `/memory-compact --dry-run` | Preview what would happen without changing files |

---

## Workflow

### Step 1: Show current stats

Run: `python3 .memory/scripts/compact_cli.py --stats`

Report the waste ratio and entry counts to the user.

### Step 2: Run compaction (if needed)

If waste ratio > 1.0:

Run: `python3 .memory/scripts/compact_cli.py`

### Step 3: Report results

Show:
- Lines before → after
- Entries kept vs archived
- Archive quarters touched
- Duration

---

## What it does

1. Reads all lines from `events.jsonl`
2. Resolves latest-wins (keeps newest version of each entry ID)
3. Filters out deprecated entries
4. Archives removed lines to `.memory/archive/events_YYYYQN.jsonl` (by quarter)
5. Atomically rewrites `events.jsonl` (clean, sorted by `created_at`)
6. Resets vectordb sync cursor (forces re-sync on next pipeline run)
7. Logs to `.memory/archive/compaction_log.jsonl`

## Safety

- **Atomic write**: Uses `os.replace()` — crash-safe on macOS/Linux
- **Append-only archive**: Never overwrites archive files
- **Audit trail**: Every compaction logged with timestamp and counts
- **Auto-triggered**: Also runs automatically via Stop hook when waste ratio exceeds threshold
