# /memory-plan — Working Memory Session Management

## Purpose

Manage short-term working memory for multi-step tasks. Working memory
maintains task plans, findings, and progress logs in `.memory/working/`.

This complements long-term EF Memory (events.jsonl) — think of it as
RAM vs hard disk. Working memory is session-scoped and gitignored;
lessons discovered during work can be harvested into long-term memory.

---

## Commands

### Start a new session

```
/memory-plan <task description>
```

Creates three files in `.memory/working/`:
- `task_plan.md` — Phases, acceptance criteria, progress tracking
- `findings.md` — Discoveries + **auto-prefill from EF Memory**
- `progress.md` — Session log of actions, errors, decisions

**Auto-prefill**: On start, searches EF Memory for entries relevant to the
task description and injects them into `findings.md` under "Pre-loaded Context".

### Resume an existing session

```
/memory-plan resume
```

Reads `task_plan.md` and `progress.md` to summarize current state:
- Current phase and progress
- Last recorded action
- Number of findings

### Check session status

```
/memory-plan status
```

Shows active/inactive status, phase progress, and file stats.

### Harvest memory candidates

```
/memory-plan harvest
```

Scans `findings.md` and `progress.md` for memory-worthy patterns:
- `LESSON:` / `CONSTRAINT:` / `DECISION:` / `WARNING:` markers
- `MUST` / `NEVER` / `ALWAYS` statements
- Error/Fix patterns

Returns candidates for `/memory-save` — does NOT auto-persist.

### Clear session

```
/memory-plan clear
```

Removes all working memory files. Use after task completion.

---

## During Work

While a working memory session is active:

1. **Read the plan** before major operations — check `task_plan.md`
2. **Update progress** — add actions, errors, and decisions to `progress.md`
3. **Record findings** — add discoveries to `findings.md`
4. **Mark phases done** — update phase headers with `[DONE]` when complete

### Recording patterns for harvest

Use these markers in `findings.md` or `progress.md` for automatic extraction:

```
LESSON: Rolling window calculations must use shift(1) before aggregation
CONSTRAINT: API responses must include cache TTL headers
DECISION: Using SQLite for vector storage instead of external service
WARNING: Feature pipeline has O(n²) complexity for large datasets
```

`MUST` / `NEVER` / `ALWAYS` statements are also automatically detected.

---

## Lifecycle

```
/memory-plan "refactor auth module"
    ↓
① Auto-prefill: EF Memory → findings.md (relevant memories injected)
    ↓
② Work: Claude updates task_plan.md + progress.md + findings.md
    ↓
③ Task complete: /memory-plan harvest
    ↓
④ Review candidates → /memory-save to persist lessons
    ↓
⑤ /memory-plan clear (clean up)
```

---

## CLI Usage

```bash
python3 .memory/scripts/working_memory_cli.py start "task description"
python3 .memory/scripts/working_memory_cli.py resume
python3 .memory/scripts/working_memory_cli.py status
python3 .memory/scripts/working_memory_cli.py harvest
python3 .memory/scripts/working_memory_cli.py clear
python3 .memory/scripts/working_memory_cli.py read-plan
```

---

## Configuration

In `.memory/config.json` under `v3`:

| Key | Default | Description |
|-----|---------|-------------|
| `working_memory_dir` | `.memory/working` | Working files directory |
| `prefill_on_plan_start` | `true` | Auto-search EF Memory on session start |
| `max_prefill_entries` | `5` | Max entries to inject into findings.md |
| `harvest_on_compact` | `true` | Remind to harvest before context compaction |
