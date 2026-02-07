# /memory-init — Initialize EF Memory auto-startup

## Purpose

Generate or update the auto-startup files that make every Claude Code session
aware of the EF Memory system. Run this once when first adding EF Memory to a
project, or re-run to update after configuration changes.

---

## What it generates

| File | Purpose | Existing file handling |
|------|---------|----------------------|
| `CLAUDE.md` | Tier 1 auto-load — session awareness | Appends EF Memory section (preserves existing content) |
| `.claude/rules/ef-memory-startup.md` | Tier 2 auto-load — brief rule | Creates or overwrites (EFM-owned) |
| `.claude/hooks.json` | Pre-compact reminder | Merges EF Memory hook (preserves other hooks) |
| `.claude/settings.local.json` | Permission whitelist | Merges EFM permissions (preserves existing) |

---

## Usage

Run the init CLI:

```bash
# Standard init (current project)
python3 .memory/scripts/init_cli.py

# Preview without writing files
python3 .memory/scripts/init_cli.py --dry-run

# Force update existing EF Memory sections
python3 .memory/scripts/init_cli.py --force

# Init a different project
python3 .memory/scripts/init_cli.py --target /path/to/project
```

---

## Behavior

### For new projects (no existing files)
- Creates all 4 files from templates
- Interpolates entry count from `.memory/events.jsonl`
- Respects `automation.human_review_required` config

### For existing projects (files already present)
- **CLAUDE.md**: Appends EF Memory section at end with `---` separator.
  If EF Memory section already exists, skips (use `--force` to update).
- **hooks.json**: Reads existing hooks, adds EF Memory `pre-compact` hook
  if not present. Never duplicates.
- **settings.local.json**: Reads existing permissions, merges EFM-specific
  entries. Never removes existing permissions.
- **ef-memory-startup.md**: Always written (EFM-owned file).

### Post-init scan
After writing files, scans the project for advisory suggestions:
- Documents in `docs/` that could be imported via `/memory-import`
- Missing `.gitignore` entries for `.memory/working/` and `vectors.db`
- High-value import targets (INCIDENTS.md, ADR, decisions)

---

## Re-running

Init is idempotent. Running it again:
- Skips files with existing EF Memory sections (unless `--force`)
- Merges safely into hooks.json and settings.local.json
- Updates suggestions based on current project state

Use `--force` to refresh EF Memory sections (e.g., after config changes
or version upgrades).

---

## Output

```
EF Memory Init — /path/to/project

Created:
  + CLAUDE.md
  + .claude/rules/ef-memory-startup.md

Merged:
  ~ .claude/hooks.json
  ~ .claude/settings.local.json

Suggestions:
  > Found 12 documents in docs/ — consider /memory-import to extract knowledge
  > Consider adding to .gitignore: .memory/working/

Done (4 files processed, 15ms)
```
