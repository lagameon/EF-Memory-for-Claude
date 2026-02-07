# /memory-scan — Batch document scanning and memory extraction

## Purpose

Scan a project's document tree, discover importable content, and extract
memory candidates from multiple documents in a single session. This is
the batch counterpart of `/memory-import` (single document).

- **Input**: Glob pattern (optional) or default doc roots from config
- **Output**: Discovered documents → user selection → extracted MEMORY ENTRY blocks → validated & persisted

---

## Human Review Mode

**Check `.memory/config.json` → `automation.human_review_required`:**

- **`true` (default)**: After extraction and validation, display all candidates for review. Do NOT write to `events.jsonl` unless the user explicitly requests it.
- **`false`**: After extraction and validation, directly append valid entries to `events.jsonl` and run the automation pipeline.

---

## Workflow

### Step 1: Discover Documents

Run the scanner CLI to find candidate documents:

```bash
# Default: scan configured doc_roots with supported_sources patterns
python3 .memory/scripts/scan_cli.py discover --json

# If the user provided a specific glob pattern:
python3 .memory/scripts/scan_cli.py discover --json --pattern "<user_pattern>"
```

Parse the JSON output. Present the user a numbered list:

```
/memory-scan

Scanning project for importable documents...

Found <N> candidate documents:

  #  | Score | Path                              | Type   | Status
  ---|-------|-----------------------------------|--------|--------
  1  | 0.95  | docs/INCIDENTS.md                 | md     | New
  2  | 0.88  | docs/DECISIONS.md                 | md     | 3 entries exist
  3  | 0.75  | docs/architecture/ARCHITECTURE.md | md     | New
  4  | 0.60  | CLAUDE.md                         | md     | 1 entry exists
  ...

Enter numbers to import (e.g., "1,2,3"), "all", or "new" (only unimported):
```

- **"new"** = only docs with `import_count == 0`
- **"all"** = every discovered document
- **Numbers** = specific documents by their row number

### Step 2: Wait for User Selection

The user selects which documents to process. If they provide no input, prompt them.

### Step 3: Extract from Each Document

For EACH selected document, **IN ORDER**:

1. Read the full document content using the Read tool
2. Apply the Extraction Rules below to identify memory candidates
3. For each candidate, produce a MEMORY ENTRY block (format below)
4. Accumulate all candidates

After processing each document, output a progress line:

```
--- Document 1/3: docs/INCIDENTS.md ---
Extracted: 2 candidates
  - [Hard/S1] Rolling statistics without shift(1) caused leakage
  - [Soft/S3] Consider caching API responses for dev speed
```

### Step 4: Convert to JSON and Validate

After ALL documents are processed, convert each MEMORY ENTRY into a JSON object matching the events.jsonl schema:

```json
{
  "id": "<type>-<slug>-<8hex>",
  "type": "<decision|lesson|constraint|risk|fact>",
  "classification": "<hard|soft>",
  "severity": "<S1|S2|S3>",
  "title": "<title>",
  "content": ["<point1>", "<point2>", ...],
  "rule": "<MUST/NEVER statement or null>",
  "implication": "<consequence or null>",
  "verify": "<check command or null>",
  "source": ["<normalized source>"],
  "tags": ["<tag1>", "<tag2>"],
  "created_at": "<ISO 8601 UTC>",
  "last_verified": null,
  "deprecated": false,
  "_meta": {}
}
```

**ID format**: `{type}-{snake_case_slug}-{random_8_hex}`
- Slug: derive from title, lowercase, underscores, max 30 chars
- Hex: 8 random hex characters

Collect all entry JSON objects into an array and pipe through validation:

```bash
echo '<JSON array of entries>' | python3 .memory/scripts/scan_cli.py validate
```

Parse the validation result and report:

```
========================================
SCAN VALIDATION REPORT
========================================
Total candidates:  <N>
  Valid:           <N>
  Duplicates:      <N> (against existing memory or within batch)
  Invalid:         <N> (schema errors)

Duplicates found:
  - "<title>" ~ existing entry <id> (similarity: 0.92)

Invalid entries:
  - "<title>": Missing required field: rule
```

### Step 5: Persist or Review

**When `human_review_required: true`:**

Display all valid candidates grouped by source document. Tell the user:

```
⚠️ REVIEW REQUIRED (human_review_required: true)

<N> valid candidates ready. No files have been modified.

Options:
  - "save all" — persist all valid entries
  - "save 1,3,5" — persist specific candidates by number
  - Edit individual entries before saving
  - "cancel" — discard all
```

When the user approves, pipe the approved entries through commit:

```bash
echo '<JSON array of approved entries>' | python3 .memory/scripts/scan_cli.py commit
```

**When `human_review_required: false`:**

Directly pipe valid entries through commit:

```bash
echo '<JSON array of valid entries>' | python3 .memory/scripts/scan_cli.py commit
```

Report:

```
========================================
SCAN COMPLETE
========================================
Documents scanned:    <N>
Entries extracted:    <N>
Entries written:      <N>
Duplicates skipped:   <N>
Invalid skipped:      <N>
Pipeline:             [OK] sync + rules
```

---

## Extraction Rules

### MUST Extract

| Content Pattern | Maps To | Required Fields |
|----------------|---------|-----------------|
| **Root Cause** / error analysis | `Content` + `Implication` | What went wrong, why it matters |
| **Fix** / solution / resolution | `Rule` | MUST/NEVER statement derived from fix |
| **Decision + Rationale** | `Rule` + `Content` | What was decided and why |
| **Constraint / Invariant** | `Rule` + `Implication` | What must hold true and what breaks |
| **Regression Check** / verification | `Verify` | One-line command or observable check |
| **Lessons Learned** / takeaways | `Content` | Key actionable points (max 4) |
| **Breaking Change** / migration | `Rule` + `Implication` | What changed and what breaks |

### MUST NOT Extract

| Content Type | Reason |
|--------------|--------|
| Timeline / chronology | No reuse value; context-specific |
| Raw logs / stack traces | Noise; not actionable |
| File listings (unless constraint) | Volatile; likely outdated |
| Estimated time / effort | Not a rule or fact |
| Intermediate discussion | Not a conclusion |
| Agent handoff notes | Session-specific |
| Opinions without evidence | Violates evidence-first principle |

### Extraction Heuristics

```
1. If "Fix", "Solution", "Resolution" section → derive Rule
2. If "Root Cause", "Why", "Analysis" section → derive Content + Implication
3. If "Verification", "Regression", "Test" section → derive Verify
4. If "Decision", "Chosen approach", "We decided" → derive Rule + Implication
5. If "Constraint", "MUST", "NEVER", "Invariant" → derive Rule
6. If "Risk", "Warning", "Caveat" → derive Implication
7. If error caused production impact → Severity = S1, Classification = Hard
8. If architectural constraint → Classification = Hard
9. If best practice / preference → Classification = Soft
```

---

## Source Normalization

| Level | Format | When to Use |
|-------|--------|-------------|
| **A (Ideal)** | `docs/DECISIONS.md#DEC-057:L12-L45` | When line numbers are verifiable |
| **B (Acceptable)** | `docs/DECISIONS.md#DEC-057` | When exact lines cannot be determined |
| **C (Minimum)** | `docs/DECISIONS.md` | When no heading anchor is available |

**Do NOT invent line numbers. An anchor without lines is better than wrong lines.**

---

## Document-Specific Guidance

### Incident Records (INCIDENTS.md, postmortems/)

```
Section "Root Cause" → Content + Implication
Section "Fix" → Rule (derive MUST/NEVER)
Section "Regression" → Verify
```

### Decision Records (DECISIONS.md, ADR/)

```
Section "Decision" → Rule
Section "Context" + "Rationale" → Content
Section "Consequences" → Implication
Status "Accepted" / "Superseded" → Classification guidance
```

### Architecture Docs

```
"MUST" / "NEVER" / "ALWAYS" statements → Rule
Diagrams with labeled constraints → Content
"If violated..." patterns → Implication
```

### Runbooks / SOPs

```
"Before deploying..." → Rule (MUST check)
"If X happens..." → Risk entry
"Never do Y in production" → Constraint entry
```

### Code Comments

```
# LESSON: → lesson entry
# CONSTRAINT: or # INVARIANT: → constraint entry
# WARNING: or # DANGER: → risk entry
# DECISION: or # WHY: → decision entry
```

---

## Quality Gates

### Automatic Rejection

```
REJECT if: No Rule AND no Implication can be derived
REJECT if: No actionable content exists (purely descriptive)
REJECT if: Source cannot be identified or verified
```

### Warnings

```
WARN if: Content exceeds 6 bullet points (likely too verbose)
WARN if: No verification method can be suggested
WARN if: Entry duplicates existing memory (check /memory-search first)
```

---

## Guardrails

### Hard Constraints (always apply)

```
- NEVER process documents without user confirming selection first
- NEVER skip the batch validation/dedup step
- NEVER write to events.jsonl if human_review_required is true (unless user explicitly approves)
- ALWAYS validate schema before writing
- ALWAYS run pipeline after writing
- NEVER invent line numbers or sources
- NEVER create entries without valid source and Rule/Implication
```

### Performance

```
- Process documents ONE AT A TIME to manage context window
- For large documents (>500 lines), focus on sections with headings matching extraction patterns
- Maximum documents per scan session: controlled by scan.max_documents config (default: 20)
- If more documents found than limit, suggest running multiple scans with narrower patterns
```

---

## Config

Reads from `.memory/config.json`:

| Key | Purpose |
|-----|---------|
| `import.supported_sources` | File patterns to scan (default: `*.md`, `*.py`, `*.ts`, `*.js`, `*.go`) |
| `import.doc_roots` | Default directories/files to scan (default: `docs/`, `CLAUDE.md`, `README.md`) |
| `scan.exclude_patterns` | Glob patterns to skip (node_modules, .git, etc.) |
| `scan.max_documents` | Maximum docs per session (default: 20) |
| `scan.relevance_keywords` | Keywords used for scoring document relevance |
| `scan.high_value_filenames` | Filenames that get a bonus relevance score |
| `automation.human_review_required` | Review toggle |
| `automation.dedup_threshold` | Text similarity threshold for duplicate detection |

---

## Usage

```
# Default scan (configured doc_roots)
/memory-scan

# Scan with specific pattern
/memory-scan docs/**/*.md

# Scan all markdown files in project
/memory-scan **/*.md

# Scan code files for comments
/memory-scan src/**/*.py
```

---

## Version

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-02-07 | Initial design — batch document scanning |
