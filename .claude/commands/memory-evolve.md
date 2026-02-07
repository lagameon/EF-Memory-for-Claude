# /memory-evolve — Memory Health & Evolution Analysis (Read-only)

## Purpose

Analyze memory health: confidence scoring, duplicate detection, deprecation candidates, and merge suggestions. Helps maintain a clean, trustworthy memory store over time.

**This command performs analysis only. It NEVER modifies events.jsonl or any file.**

---

## When to use

- Periodic hygiene check (monthly or after large import)
- Before trusting old entries in decisions
- After noticing duplicate or contradictory memories
- When memory store grows large (50+ entries)

---

## Input

| Format | Description |
|--------|-------------|
| `/memory-evolve` | Full evolution report (default) |
| `/memory-evolve --duplicates` | Find duplicate entry groups only |
| `/memory-evolve --confidence` | Score all entries by confidence |
| `/memory-evolve --deprecations` | Suggest entries for deprecation |
| `/memory-evolve --merges` | Suggest entries to merge |
| `/memory-evolve --id=<id>` | Confidence breakdown for single entry |

---

## Steps

1. Run the evolution CLI:
   ```bash
   python3 .memory/scripts/evolution_cli.py [flags]
   ```
   Pass through any flags from the user input (e.g., `--duplicates`, `--id=<id>`).

2. Parse the text output.

3. Present the report to the user:
   - **Health score** (0.0–1.0): overall memory store quality
   - **Confidence distribution**: High / Medium / Low counts
   - **Duplicate groups**: entries with similar content (candidates for merge)
   - **Deprecation candidates**: low-confidence entries with stale sources
   - **Merge suggestions**: which entry to keep, which to deprecate

4. If actionable items are found, suggest next steps:
   - For duplicates: "Consider merging with `/memory-save` — keep the better-sourced entry"
   - For deprecations: "Review these entries; deprecate with `/memory-save` if no longer valid"
   - For low confidence: "Re-verify sources or update `last_verified`"

---

## Report Sections

### Health Score

| Score | Meaning |
|-------|---------|
| 0.8–1.0 | Healthy — few issues |
| 0.5–0.8 | Needs attention — some stale/duplicate entries |
| < 0.5 | Unhealthy — significant cleanup needed |

### Confidence Scoring

Each entry gets a confidence score (0.0–1.0) based on:

| Factor | Weight | Description |
|--------|--------|-------------|
| Source quality | 30% | Code/function > markdown > commit > PR > unknown |
| Age factor | 30% | Decays over time (half-life: 120 days) |
| Verification boost | 15% | Bonus for entries with `last_verified` set |
| Source validity | 25% | Whether source files still exist |

### Duplicate Detection

Groups entries by text similarity. In hybrid mode (embeddings enabled), also uses vector similarity.

### Deprecation Suggestions

Flags entries that are:
- Below confidence threshold (default: 0.3)
- Have missing source files
- Are very old with no verification

### Merge Suggestions

For each duplicate group, suggests:
- Which entry to **keep** (highest confidence, best sources)
- Which entries to **deprecate** (lower quality duplicates)

---

## Guardrails (Mandatory)

```
┌────────────────────────────────────────────────────────────────────┐
│ HARD CONSTRAINTS — VIOLATION = COMMAND FAILURE                     │
├────────────────────────────────────────────────────────────────────┤
│ 1. NEVER write to events.jsonl or any file                         │
│ 2. NEVER auto-deprecate or auto-merge entries                      │
│ 3. NEVER execute suggested actions without user confirmation       │
│ 4. ALWAYS report "No files were modified" at end of output         │
│ 5. ALWAYS let the user decide which actions to take                │
└────────────────────────────────────────────────────────────────────┘
```

---

## Example Output

```
/memory-evolve

========================================
MEMORY EVOLUTION REPORT
========================================
Total entries:     12
Active:            11
Deprecated:        1
Health score:      0.742
Avg confidence:    0.681

Confidence:  High=5  Medium=4  Low=2

Duplicates: 1 group(s) [text_only]
  - ['lesson-auth-a1b2c3d4', 'lesson-auth-e5f6a7b8'] (avg: 0.91)

Deprecation candidates: 1
  [review] risk-deploy-11223344 (confidence: 0.28)

Merge suggestions: 1
  Keep lesson-auth-a1b2c3d4, deprecate ['lesson-auth-e5f6a7b8']

========================================
SUGGESTED ACTIONS
========================================
1. Review duplicate group: auth lessons may be mergeable
2. Review risk-deploy-11223344 — confidence below threshold
3. Consider updating last_verified on 2 low-confidence entries

No files were modified. This is a read-only report.
```

---

## Version

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-02-07 | Initial specification (read-only analysis) |
