# /memory-reason — Memory Reasoning & Cross-Analysis (Read-only)

## Purpose

Cross-memory reasoning: find correlations between entries, detect contradictions, suggest knowledge synthesis, and assess risks in context. Supports both heuristic-only and LLM-enriched modes.

**This command performs analysis only. It NEVER modifies events.jsonl or any file.**

---

## When to use

- Discover hidden connections between separate memories
- Detect contradicting constraints or lessons
- Synthesize related memories into higher-order principles
- Before major changes — assess risk across all relevant memories

---

## Input

| Format | Description |
|--------|-------------|
| `/memory-reason` | Full reasoning report (default) |
| `/memory-reason --correlations` | Find cross-memory correlations |
| `/memory-reason --contradictions` | Detect contradicting entries |
| `/memory-reason --syntheses` | Suggest knowledge synthesis |
| `/memory-reason --risks "query"` | Risk assessment for a specific topic |
| `/memory-reason --no-llm` | Force heuristic-only mode |

---

## Steps

1. Run the reasoning CLI:
   ```bash
   python3 .memory/scripts/reasoning_cli.py [flags]
   ```
   Pass through any flags from the user input.

2. Parse the text output.

3. Present the report to the user:
   - **Mode**: `heuristic` (tag/keyword matching) or `llm_enriched` (LLM-assisted)
   - **Correlations**: groups of entries that are related
   - **Contradictions**: pairs of entries that conflict
   - **Synthesis**: opportunities to create higher-order principles
   - **Risks**: context-aware risk annotations (if `--risks` used)

4. If actionable items are found, suggest next steps:
   - For contradictions: "These entries conflict — review and resolve with `/memory-save`"
   - For synthesis: "Consider creating a new principle entry that supersedes these"
   - For risks: "Pay attention to these constraints before proceeding"

---

## Modes

### Heuristic Mode (default when `reasoning.enabled=false`)

Uses tag overlap, keyword matching, and structural analysis. No external API calls.

| Analysis | Method |
|----------|--------|
| Correlations | Shared tags, overlapping source files, same domain |
| Contradictions | Opposing keywords (MUST vs NEVER), same scope |
| Synthesis | Groups with 3+ entries sharing tags/domains |

### LLM-Enriched Mode (when `reasoning.enabled=true`)

Uses an LLM provider for deeper semantic analysis. Configurable in `.memory/config.json`:

```json
"reasoning": {
  "enabled": true,
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514"
}
```

| Analysis | Enhancement |
|----------|-------------|
| Correlations | Semantic similarity beyond keywords |
| Contradictions | Nuanced conflict detection |
| Synthesis | Generates proposed titles and principles |

---

## Report Sections

### Correlations

Groups of related entries with:
- **Relationship type**: shared domain, causal chain, complementary constraints
- **Strength** (0.0–1.0): how strongly related
- **Explanation**: why these entries are connected

### Contradictions

Pairs of entries that may conflict:
- **Type**: direct (explicit conflict) or semantic (implied tension)
- **Confidence** (0.0–1.0): how likely this is a real contradiction
- **Explanation**: what the conflict is about

### Synthesis Suggestions

Opportunities to create higher-order entries:
- **Source entries**: which entries contribute
- **Proposed title**: suggested title for new principle (LLM mode)
- **Proposed principle**: the synthesized insight (LLM mode)
- **Rationale**: why these should be combined

### Risk Assessment (`--risks "query"`)

Context-aware annotations for a specific topic:
- **Risk level**: high / medium / low / info
- **Annotation**: what to watch out for
- **Related entries**: connected memories to consider

---

## Guardrails (Mandatory)

```
┌────────────────────────────────────────────────────────────────────┐
│ HARD CONSTRAINTS — VIOLATION = COMMAND FAILURE                     │
├────────────────────────────────────────────────────────────────────┤
│ 1. NEVER write to events.jsonl or any file                         │
│ 2. NEVER auto-create, merge, or deprecate entries                  │
│ 3. NEVER make LLM calls without user awareness of mode             │
│ 4. ALWAYS report "No files were modified" at end of output         │
│ 5. ALWAYS indicate mode (heuristic vs llm_enriched) in output      │
│ 6. ALWAYS let the user decide which actions to take                │
└────────────────────────────────────────────────────────────────────┘
```

---

## Example Output

```
/memory-reason

========================================
MEMORY REASONING REPORT  [heuristic]
========================================
Total entries: 12
LLM calls:    0

Correlations: 2 group(s) [heuristic]
  - shared_domain: ['constraint-deploy-aabb1122', 'risk-deploy-11223344'] (0.75)
  - causal_chain: ['lesson-inc034-d1760930', 'lesson-inc036-e3f13b37'] (0.68)

Contradictions: 1 pair(s) [heuristic]
  - [direct] constraint-auth-99887766 vs lesson-auth-a1b2c3d4 (0.82)
    "Auth constraint says MUST use JWT, but lesson recommends session cookies"

Synthesis: 1 suggestion(s) [heuristic]
  - (needs LLM): ['lesson-inc034-d1760930', 'lesson-inc035-800ae2e3', 'lesson-inc036-e3f13b37']

========================================
SUGGESTED ACTIONS
========================================
1. Review auth contradiction — entries may need reconciliation
2. Consider enabling LLM mode for richer synthesis titles
3. Deployment entries are correlated — review together before changes

No files were modified. This is a read-only report.
```

---

## Version

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-02-07 | Initial specification (read-only analysis) |
