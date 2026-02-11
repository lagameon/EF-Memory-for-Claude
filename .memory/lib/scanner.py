"""
EF Memory V3 — Document Scanner

Document discovery, relevance scoring, batch deduplication,
and batch writing for multi-document import workflows.

Used by /memory-scan command via scan_cli.py.

Reuses:
  - auto_verify.validate_schema — schema validation
  - auto_verify.check_duplicates, _load_entries_latest_wins — dedup
  - text_builder.build_dedup_text — similarity input

No external dependencies — pure Python stdlib + internal modules.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .auto_verify import (
    DedupResult,
    ValidationResult,
    _load_entries_latest_wins,
    check_duplicates,
    validate_schema,
)

logger = logging.getLogger("efm.scanner")


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_EXCLUDE = [
    "**/node_modules/**",
    "**/.git/**",
    "**/venv/**",
    "**/__pycache__/**",
    "**/.memory/**",
    "**/dist/**",
    "**/build/**",
]

_DEFAULT_KEYWORDS = [
    "MUST", "NEVER", "ALWAYS", "CONSTRAINT", "INVARIANT",
    "LESSON", "DECISION", "ROOT CAUSE", "FIX", "RISK",
    "WARNING", "BREAKING CHANGE", "MIGRATION",
]

_DEFAULT_HIGH_VALUE = [
    "INCIDENTS.md", "DECISIONS.md", "ARCHITECTURE.md",
    "RUNBOOK.md", "CHANGELOG.md", "CLAUDE.md", "README.md",
]

_DEFAULT_MAX_DOCUMENTS = 20

# Extension base scores (higher = more likely to contain importable knowledge)
_EXTENSION_SCORES: Dict[str, float] = {
    ".md": 0.30,
    ".rst": 0.25,
    ".txt": 0.15,
    ".py": 0.10,
    ".ts": 0.10,
    ".js": 0.08,
    ".go": 0.08,
}

_SAMPLE_LINES = 50  # Lines to sample for keyword scoring
_MAX_FILE_SIZE_BYTES = 5_242_880  # 5 MB default
_MAX_LINE_COUNT = 100_000


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DocumentInfo:
    """Information about a discovered document."""
    path: str = ""           # Absolute path
    rel_path: str = ""       # Relative to project root
    size_bytes: int = 0
    line_count: int = 0
    doc_type: str = ""       # File extension without dot
    relevance_score: float = 0.0
    snippet: str = ""        # First heading + first content line
    already_imported: bool = False
    import_count: int = 0    # Existing entries sourcing this file


@dataclass
class ScanReport:
    """Result of document discovery."""
    documents: List[DocumentInfo] = field(default_factory=list)
    total_scanned: int = 0
    total_excluded: int = 0
    skipped_oversized: int = 0
    duration_ms: float = 0.0


@dataclass
class BatchValidateResult:
    """Result of batch validation and deduplication."""
    valid: List[dict] = field(default_factory=list)
    duplicates: List[Tuple[dict, DedupResult]] = field(default_factory=list)
    invalid: List[Tuple[dict, ValidationResult]] = field(default_factory=list)
    total: int = 0
    duration_ms: float = 0.0


@dataclass
class BatchWriteResult:
    """Result of batch writing to events.jsonl."""
    written_count: int = 0
    entry_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Document discovery
# ---------------------------------------------------------------------------

def discover_documents(
    project_root: Path,
    config: dict,
    pattern: Optional[str] = None,
) -> ScanReport:
    """
    Discover candidate documents for memory extraction.

    Uses import.supported_sources and import.doc_roots from config,
    filtered by scan.exclude_patterns. Scores each document for
    relevance and annotates with existing import count.

    Args:
        project_root: Project root directory
        config: Full EF Memory config dict
        pattern: Optional glob override (e.g. "docs/**/*.md")
    """
    start_time = time.monotonic()
    report = ScanReport()

    scan_config = config.get("scan", {})
    import_config = config.get("import", {})

    exclude_patterns = scan_config.get("exclude_patterns", _DEFAULT_EXCLUDE)
    max_docs = scan_config.get("max_documents", _DEFAULT_MAX_DOCUMENTS)

    # Determine file patterns to search
    if pattern:
        # User-provided pattern overrides defaults
        file_patterns = [pattern]
        search_roots = [project_root]
    else:
        supported = import_config.get("supported_sources", ["*.md", "*.py", "*.ts", "*.js", "*.go"])
        doc_roots = import_config.get("doc_roots", ["docs/"])
        # Search each doc_root with each supported extension
        file_patterns = supported
        search_roots = []
        for root in doc_roots:
            root_path = project_root / root
            if root_path.is_file():
                # Direct file reference (e.g. "CLAUDE.md")
                search_roots.append(root_path)
            elif root_path.is_dir():
                search_roots.append(root_path)

    # Collect all candidate paths
    candidates: Dict[str, Path] = {}  # rel_path -> abs_path

    for search_root in search_roots:
        if search_root.is_file():
            # Direct file reference
            rel = str(search_root.relative_to(project_root))
            candidates[rel] = search_root
            continue

        for fp in file_patterns:
            glob_pattern = f"**/{fp}" if not fp.startswith("**/") else fp
            try:
                for match in search_root.glob(glob_pattern):
                    if not match.is_file():
                        continue
                    rel = str(match.relative_to(project_root))
                    candidates[rel] = match
            except (OSError, ValueError):
                continue

    # Filter out excluded paths
    filtered: Dict[str, Path] = {}
    for rel, abs_path in candidates.items():
        excluded = False
        for exc in exclude_patterns:
            # Simple pattern matching: convert glob to a basic check
            if _matches_exclude(rel, exc):
                excluded = True
                break
        if not excluded:
            filtered[rel] = abs_path
        else:
            report.total_excluded += 1

    report.total_scanned = len(filtered)

    # Check already-imported status
    events_path = project_root / ".memory" / "events.jsonl"
    import_map = check_already_imported(events_path)

    # Score and build DocumentInfo for each file
    docs: List[DocumentInfo] = []
    skipped_oversized = 0
    for rel, abs_path in filtered.items():
        try:
            info = _build_document_info(abs_path, rel, config, import_map)
            if info is None:
                skipped_oversized += 1
                continue
            docs.append(info)
        except (OSError, UnicodeDecodeError):
            continue

    # Sort by relevance descending
    docs.sort(key=lambda d: d.relevance_score, reverse=True)

    # Apply max_documents limit
    report.documents = docs[:max_docs]
    report.skipped_oversized = skipped_oversized
    report.duration_ms = (time.monotonic() - start_time) * 1000

    return report


def _build_document_info(
    abs_path: Path,
    rel_path: str,
    config: dict,
    import_map: Dict[str, int],
) -> Optional[DocumentInfo]:
    """Build a DocumentInfo for a single file. Returns None if oversized."""
    stat = abs_path.stat()
    size = stat.st_size

    # File size safety check
    max_size = config.get("scan", {}).get("max_file_size_bytes", _MAX_FILE_SIZE_BYTES)
    if size > max_size:
        logger.info("Skipping oversized file %s (%d bytes > %d limit)", rel_path, size, max_size)
        return None

    # Read content sample
    content_sample = ""
    line_count = 0
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = []
            for i, line in enumerate(f):
                line_count += 1
                if i < _SAMPLE_LINES:
                    lines.append(line)
                if line_count >= _MAX_LINE_COUNT:
                    break
            content_sample = "".join(lines)
    except OSError:
        pass

    # Extract snippet (first heading + first non-empty line)
    snippet = _extract_snippet(content_sample)

    # Score relevance
    score = score_relevance(abs_path, content_sample, config)

    # Check import status
    count = import_map.get(rel_path, 0)

    ext = abs_path.suffix.lstrip(".")

    return DocumentInfo(
        path=str(abs_path),
        rel_path=rel_path,
        size_bytes=size,
        line_count=line_count,
        doc_type=ext,
        relevance_score=round(score, 2),
        snippet=snippet,
        already_imported=count > 0,
        import_count=count,
    )


def _extract_snippet(content: str) -> str:
    """Extract first heading and first non-empty content line."""
    heading = ""
    first_line = ""

    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if not heading and stripped.startswith("#"):
            heading = stripped
        elif heading and not first_line:
            first_line = stripped[:120]
            break
        elif not heading:
            first_line = stripped[:120]
            break

    parts = [p for p in [heading, first_line] if p]
    return " | ".join(parts) if parts else ""


def _matches_exclude(rel_path: str, pattern: str) -> bool:
    """
    Simple check if rel_path matches an exclude pattern.

    Supports:
      - **/dir/** → any path containing /dir/
      - **/*.ext → any file ending with .ext
      - dir/** → path starting with dir/
    """
    # Normalize separators
    rel = rel_path.replace(os.sep, "/")
    pat = pattern.replace(os.sep, "/")

    # **/dir/** → check if /dir/ appears anywhere (or starts with dir/)
    if pat.startswith("**/") and pat.endswith("/**"):
        segment = pat[3:-3]  # e.g. "node_modules"
        return f"/{segment}/" in f"/{rel}" or rel.startswith(f"{segment}/")

    # **/*.ext → check file extension
    if pat.startswith("**/") and "*" not in pat[3:]:
        suffix = pat[3:]  # e.g. "*.md" — but this case is unlikely for excludes
        if suffix.startswith("*."):
            ext = suffix[1:]  # ".md"
            return rel.endswith(ext)

    # dir/** → starts with dir/
    if pat.endswith("/**"):
        prefix = pat[:-3]
        return rel.startswith(prefix + "/") or rel == prefix

    # Exact match fallback
    return rel == pat


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------

def score_relevance(
    file_path: Path,
    content_sample: str,
    config: dict,
) -> float:
    """
    Score a document's relevance for memory extraction (0.0–1.0).

    Components:
      - Extension base score (0.0–0.30)
      - Filename heuristics (0.0–0.30)
      - Keyword density (0.0–0.40)
    """
    scan_config = config.get("scan", {})
    keywords = scan_config.get("relevance_keywords", _DEFAULT_KEYWORDS)
    high_value = scan_config.get("high_value_filenames", _DEFAULT_HIGH_VALUE)

    score = 0.0

    # 1. Extension base score
    ext = file_path.suffix.lower()
    score += _EXTENSION_SCORES.get(ext, 0.05)

    # 2. Filename heuristics
    name = file_path.name
    if name in high_value:
        score += 0.30
    elif name.upper() == name and ext in (".md", ".rst", ".txt"):
        # ALL-CAPS filenames (e.g. ARCHITECTURE.md) get a smaller boost
        score += 0.15

    # 3. Keyword density in content sample
    if content_sample:
        upper_content = content_sample.upper()
        keyword_hits = 0
        for kw in keywords:
            keyword_hits += upper_content.count(kw.upper())

        # Normalize: ~10+ hits → full 0.40 score
        density_score = min(keyword_hits / 10.0, 1.0) * 0.40
        score += density_score

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Already-imported check
# ---------------------------------------------------------------------------

def check_already_imported(events_path: Path) -> Dict[str, int]:
    """
    Parse source references in events.jsonl to build a map of
    file_path → count of entries sourcing that file.

    Handles source formats:
      - path:L10-L20 → path
      - path#Heading:L10-L20 → path
      - path#Heading → path
      - path::function → path
    """
    counts: Dict[str, int] = {}

    entries = _load_entries_latest_wins(events_path)
    for entry in entries.values():
        if entry.get("deprecated", False):
            continue
        sources = entry.get("source", [])
        if isinstance(sources, str):
            sources = [sources]
        for src in sources:
            file_path = _extract_file_from_source(src)
            if file_path:
                counts[file_path] = counts.get(file_path, 0) + 1

    return counts


def _extract_file_from_source(source: str) -> Optional[str]:
    """Extract the file path portion from a normalized source reference."""
    s = source.strip()
    if not s:
        return None

    # Skip non-file sources (commit, PR)
    if s.startswith("commit ") or s.startswith("PR ") or s.startswith("PR#"):
        return None

    # path::function → path
    if "::" in s:
        return s.split("::")[0]

    # path#anchor:L10-L20 or path#anchor → path
    if "#" in s:
        return s.split("#")[0]

    # path:L10-L20 → path
    line_match = re.search(r":L\d+(-L\d+)?$", s)
    if line_match:
        return s[:line_match.start()]

    # Plain path
    return s if "/" in s or "." in s else None


# ---------------------------------------------------------------------------
# Batch validation and deduplication
# ---------------------------------------------------------------------------

def batch_validate(
    entries: List[dict],
    events_path: Path,
    config: dict,
) -> BatchValidateResult:
    """
    Validate and deduplicate a batch of entries.

    For each entry:
    1. Schema validation via validate_schema()
    2. Dedup against existing events.jsonl
    3. Cross-dedup against other entries in the batch

    Returns categorized results: valid, duplicates, invalid.
    """
    start_time = time.monotonic()
    result = BatchValidateResult(total=len(entries))

    threshold = config.get("automation", {}).get("dedup_threshold", 0.85)

    # Pre-load existing entries once
    existing = _load_entries_latest_wins(events_path)

    # Track validated entries for cross-dedup within batch
    validated_so_far: Dict[str, dict] = {}

    for entry in entries:
        entry_id = entry.get("id", "")

        # 1. Schema validation
        validation = validate_schema(entry)
        if not validation.valid:
            result.invalid.append((entry, validation))
            continue

        # 2. Dedup against existing events.jsonl
        dedup = check_duplicates(
            entry, events_path,
            threshold=threshold,
            _preloaded_entries=existing,
        )
        if dedup.is_duplicate:
            result.duplicates.append((entry, dedup))
            continue

        # 3. Cross-dedup against earlier entries in this batch
        if validated_so_far:
            cross_dedup = check_duplicates(
                entry, events_path,
                threshold=threshold,
                _preloaded_entries=validated_so_far,
            )
            if cross_dedup.is_duplicate:
                result.duplicates.append((entry, cross_dedup))
                continue

        result.valid.append(entry)
        if entry_id:
            validated_so_far[entry_id] = entry

    result.duration_ms = (time.monotonic() - start_time) * 1000
    return result


# ---------------------------------------------------------------------------
# Batch writing
# ---------------------------------------------------------------------------

def batch_write(
    entries: List[dict],
    events_path: Path,
) -> BatchWriteResult:
    """
    Append a batch of entries to events.jsonl.

    Creates events.jsonl if it doesn't exist.
    Each entry is written as a single JSON line.
    """
    result = BatchWriteResult()

    if not entries:
        return result

    # Ensure parent directory exists
    events_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(events_path, "a", encoding="utf-8") as f:
            for entry in entries:
                try:
                    line = json.dumps(entry, ensure_ascii=False)
                    f.write(line + "\n")
                    entry_id = entry.get("id", "unknown")
                    result.entry_ids.append(entry_id)
                    result.written_count += 1
                except (TypeError, ValueError) as e:
                    result.errors.append(f"Cannot serialize entry: {e}")
    except OSError as e:
        result.errors.append(f"Cannot write to {events_path}: {e}")

    return result
