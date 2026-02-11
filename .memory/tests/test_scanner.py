"""
Tests for EF Memory V3 — Document Scanner

Covers: discover_documents, score_relevance, check_already_imported,
        batch_validate, batch_write, _matches_exclude, _extract_file_from_source
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Import path setup
_MEMORY_DIR = Path(__file__).resolve().parent.parent
if str(_MEMORY_DIR) not in sys.path:
    sys.path.insert(0, str(_MEMORY_DIR))

from lib.scanner import (
    BatchValidateResult,
    BatchWriteResult,
    DocumentInfo,
    ScanReport,
    _extract_file_from_source,
    _matches_exclude,
    batch_validate,
    batch_write,
    check_already_imported,
    discover_documents,
    score_relevance,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> dict:
    """Create a minimal config for testing."""
    config = {
        "import": {
            "supported_sources": ["*.md", "*.py", "*.ts"],
            "doc_roots": ["docs/"],
        },
        "scan": {
            "exclude_patterns": ["**/node_modules/**", "**/.git/**", "**/.memory/**"],
            "max_documents": 20,
            "relevance_keywords": [
                "MUST", "NEVER", "ALWAYS", "CONSTRAINT",
                "LESSON", "DECISION", "FIX", "RISK",
            ],
            "high_value_filenames": [
                "INCIDENTS.md", "DECISIONS.md", "ARCHITECTURE.md",
                "CLAUDE.md", "README.md",
            ],
        },
        "automation": {
            "dedup_threshold": 0.85,
        },
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and k in config:
            config[k].update(v)
        else:
            config[k] = v
    return config


def _make_valid_entry(
    entry_id: str = "lesson-test_entry-aabbccdd",
    title: str = "Test entry title",
    rule: str = "MUST test everything",
    sources: list = None,
    **kwargs,
) -> dict:
    """Create a valid memory entry for testing."""
    entry = {
        "id": entry_id,
        "type": "lesson",
        "classification": "hard",
        "severity": "S2",
        "title": title,
        "content": ["Point one", "Point two"],
        "rule": rule,
        "implication": "Tests fail if not followed",
        "source": sources or ["docs/test.md#Section:L1-L10"],
        "tags": ["test"],
        "created_at": "2026-02-07T12:00:00Z",
        "last_verified": None,
        "deprecated": False,
    }
    entry.update(kwargs)
    return entry


def _write_events(events_path: Path, entries: list) -> None:
    """Write entries to events.jsonl."""
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with open(events_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _create_project(tmpdir: Path, files: dict) -> Path:
    """Create a project structure from a dict of {rel_path: content}."""
    for rel, content in files.items():
        p = tmpdir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmpdir


# ===========================================================================
# Test: _matches_exclude
# ===========================================================================

class TestMatchesExclude(unittest.TestCase):

    def test_node_modules_excluded(self):
        self.assertTrue(_matches_exclude("node_modules/foo/bar.js", "**/node_modules/**"))

    def test_nested_node_modules(self):
        self.assertTrue(_matches_exclude("src/node_modules/pkg/index.js", "**/node_modules/**"))

    def test_git_excluded(self):
        self.assertTrue(_matches_exclude(".git/config", "**/.git/**"))

    def test_normal_path_not_excluded(self):
        self.assertFalse(_matches_exclude("docs/README.md", "**/node_modules/**"))

    def test_memory_dir_excluded(self):
        self.assertTrue(_matches_exclude(".memory/events.jsonl", "**/.memory/**"))

    def test_prefix_dir_exclude(self):
        self.assertTrue(_matches_exclude("dist/bundle.js", "dist/**"))

    def test_exact_match(self):
        self.assertTrue(_matches_exclude("foo.txt", "foo.txt"))


# ===========================================================================
# Test: _extract_file_from_source
# ===========================================================================

class TestExtractFileFromSource(unittest.TestCase):

    def test_code_source(self):
        self.assertEqual(
            _extract_file_from_source("src/main.py:L10-L20"),
            "src/main.py",
        )

    def test_markdown_source(self):
        self.assertEqual(
            _extract_file_from_source("docs/INCIDENTS.md#INC-036:L553-L699"),
            "docs/INCIDENTS.md",
        )

    def test_anchor_only(self):
        self.assertEqual(
            _extract_file_from_source("docs/DECISIONS.md#DEC-057"),
            "docs/DECISIONS.md",
        )

    def test_function_source(self):
        self.assertEqual(
            _extract_file_from_source("src/auth.py::validate_token"),
            "src/auth.py",
        )

    def test_commit_source_returns_none(self):
        self.assertIsNone(_extract_file_from_source("commit 7874956"))

    def test_pr_source_returns_none(self):
        self.assertIsNone(_extract_file_from_source("PR #123"))

    def test_empty_returns_none(self):
        self.assertIsNone(_extract_file_from_source(""))

    def test_plain_path(self):
        self.assertEqual(
            _extract_file_from_source("docs/ARCHITECTURE.md"),
            "docs/ARCHITECTURE.md",
        )


# ===========================================================================
# Test: score_relevance
# ===========================================================================

class TestScoreRelevance(unittest.TestCase):

    def test_high_value_filename_boost(self):
        config = _make_config()
        score = score_relevance(
            Path("docs/INCIDENTS.md"),
            "Some content with a MUST rule",
            config,
        )
        # High-value filename gets 0.30 ext + 0.30 filename = 0.60 base
        self.assertGreater(score, 0.5)

    def test_keyword_density_scoring(self):
        config = _make_config()
        many_keywords = "MUST do this\nNEVER do that\nALWAYS check\nCONSTRAINT here\n" * 3
        few_keywords = "Some regular text without special words."

        score_high = score_relevance(Path("docs/guide.md"), many_keywords, config)
        score_low = score_relevance(Path("docs/guide.md"), few_keywords, config)
        self.assertGreater(score_high, score_low)

    def test_markdown_preferred_over_code(self):
        config = _make_config()
        content = "Some content"
        md_score = score_relevance(Path("docs/guide.md"), content, config)
        py_score = score_relevance(Path("src/main.py"), content, config)
        self.assertGreater(md_score, py_score)

    def test_empty_content_lower_score(self):
        config = _make_config()
        score_empty = score_relevance(Path("docs/empty.md"), "", config)
        score_content = score_relevance(
            Path("docs/full.md"),
            "MUST do this\nNEVER skip tests",
            config,
        )
        self.assertGreater(score_content, score_empty)

    def test_score_capped_at_one(self):
        config = _make_config()
        extreme = "MUST NEVER ALWAYS CONSTRAINT " * 50
        score = score_relevance(Path("INCIDENTS.md"), extreme, config)
        self.assertLessEqual(score, 1.0)

    def test_unknown_extension_gets_base_score(self):
        config = _make_config()
        score = score_relevance(Path("data.csv"), "MUST validate", config)
        # Unknown ext gets 0.05 base
        self.assertGreater(score, 0.0)


# ===========================================================================
# Test: check_already_imported
# ===========================================================================

class TestCheckAlreadyImported(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.events_path = self.tmpdir / ".memory" / "events.jsonl"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_detects_imported_sources(self):
        entries = [
            _make_valid_entry(
                entry_id="lesson-test1-aabbcc01",
                sources=["docs/INCIDENTS.md#INC-036:L553-L699"],
            ),
        ]
        _write_events(self.events_path, entries)
        result = check_already_imported(self.events_path)
        self.assertEqual(result.get("docs/INCIDENTS.md"), 1)

    def test_counts_multiple_entries_per_file(self):
        entries = [
            _make_valid_entry(
                entry_id="lesson-test1-aabbcc01",
                sources=["docs/INCIDENTS.md#INC-036:L10-L20"],
            ),
            _make_valid_entry(
                entry_id="lesson-test2-aabbcc02",
                sources=["docs/INCIDENTS.md#INC-037:L30-L40"],
            ),
        ]
        _write_events(self.events_path, entries)
        result = check_already_imported(self.events_path)
        self.assertEqual(result.get("docs/INCIDENTS.md"), 2)

    def test_empty_events(self):
        result = check_already_imported(self.events_path)
        self.assertEqual(result, {})

    def test_skips_deprecated(self):
        entries = [
            _make_valid_entry(
                entry_id="lesson-test1-aabbcc01",
                sources=["docs/old.md#Section"],
                deprecated=True,
            ),
        ]
        _write_events(self.events_path, entries)
        result = check_already_imported(self.events_path)
        self.assertEqual(result.get("docs/old.md", 0), 0)

    def test_handles_function_sources(self):
        entries = [
            _make_valid_entry(
                entry_id="lesson-test1-aabbcc01",
                sources=["src/auth.py::validate_token"],
            ),
        ]
        _write_events(self.events_path, entries)
        result = check_already_imported(self.events_path)
        self.assertEqual(result.get("src/auth.py"), 1)


# ===========================================================================
# Test: discover_documents
# ===========================================================================

class TestDiscoverDocuments(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_discovers_markdown_files(self):
        _create_project(self.tmpdir, {
            "docs/guide.md": "# Guide\nSome content",
            "docs/api.md": "# API\nEndpoints",
        })
        config = _make_config()
        report = discover_documents(self.tmpdir, config)
        rel_paths = [d.rel_path for d in report.documents]
        self.assertIn("docs/guide.md", rel_paths)
        self.assertIn("docs/api.md", rel_paths)

    def test_respects_exclude_patterns(self):
        _create_project(self.tmpdir, {
            "docs/guide.md": "# Guide",
            "node_modules/pkg/README.md": "# Pkg",
        })
        config = _make_config()
        # Add docs as root AND ensure node_modules is in exclude
        config["import"]["doc_roots"] = ["docs/", "node_modules/"]
        report = discover_documents(self.tmpdir, config)
        rel_paths = [d.rel_path for d in report.documents]
        self.assertIn("docs/guide.md", rel_paths)
        self.assertNotIn("node_modules/pkg/README.md", rel_paths)

    def test_relevance_ordering(self):
        _create_project(self.tmpdir, {
            "docs/INCIDENTS.md": "# Incidents\nMUST fix\nNEVER repeat\nALWAYS check",
            "docs/notes.md": "# Notes\nSome regular text here",
        })
        config = _make_config()
        report = discover_documents(self.tmpdir, config)
        self.assertEqual(len(report.documents), 2)
        # INCIDENTS.md should score higher
        self.assertEqual(report.documents[0].rel_path, "docs/INCIDENTS.md")

    def test_already_imported_annotation(self):
        _create_project(self.tmpdir, {
            "docs/guide.md": "# Guide\nContent",
        })
        events_path = self.tmpdir / ".memory" / "events.jsonl"
        _write_events(events_path, [
            _make_valid_entry(sources=["docs/guide.md#Section:L1-L10"]),
        ])
        config = _make_config()
        report = discover_documents(self.tmpdir, config)
        doc = next(d for d in report.documents if d.rel_path == "docs/guide.md")
        self.assertTrue(doc.already_imported)
        self.assertEqual(doc.import_count, 1)

    def test_empty_project(self):
        config = _make_config()
        report = discover_documents(self.tmpdir, config)
        self.assertEqual(len(report.documents), 0)

    def test_custom_glob_pattern(self):
        _create_project(self.tmpdir, {
            "docs/guide.md": "# Guide",
            "src/main.py": "# MUST validate",
            "src/lib/utils.py": "# Helper",
        })
        config = _make_config()
        report = discover_documents(self.tmpdir, config, pattern="src/**/*.py")
        rel_paths = [d.rel_path for d in report.documents]
        self.assertIn("src/main.py", rel_paths)
        self.assertIn("src/lib/utils.py", rel_paths)
        self.assertNotIn("docs/guide.md", rel_paths)

    def test_max_documents_limit(self):
        # Create more docs than the limit
        files = {f"docs/doc{i:02d}.md": f"# Doc {i}\nContent" for i in range(25)}
        _create_project(self.tmpdir, files)
        config = _make_config()
        config["scan"]["max_documents"] = 5
        report = discover_documents(self.tmpdir, config)
        self.assertLessEqual(len(report.documents), 5)
        self.assertGreater(report.total_scanned, 5)

    def test_direct_file_root(self):
        """Config doc_roots can include direct files like CLAUDE.md."""
        _create_project(self.tmpdir, {
            "CLAUDE.md": "# Project\nMUST follow these rules",
            "docs/guide.md": "# Guide",
        })
        config = _make_config()
        config["import"]["doc_roots"] = ["CLAUDE.md", "docs/"]
        report = discover_documents(self.tmpdir, config)
        rel_paths = [d.rel_path for d in report.documents]
        self.assertIn("CLAUDE.md", rel_paths)


# ===========================================================================
# Test: batch_validate
# ===========================================================================

class TestBatchValidate(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.events_path = self.tmpdir / ".memory" / "events.jsonl"
        self.events_path.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid_entries_pass(self):
        _write_events(self.events_path, [])
        entries = [
            _make_valid_entry(entry_id="lesson-alpha-aabb0001"),
            _make_valid_entry(entry_id="lesson-beta-aabb0002", title="Different title", rule="NEVER skip validation"),
        ]
        config = _make_config()
        result = batch_validate(entries, self.events_path, config)
        self.assertEqual(len(result.valid), 2)
        self.assertEqual(len(result.invalid), 0)
        self.assertEqual(len(result.duplicates), 0)

    def test_invalid_entries_flagged(self):
        _write_events(self.events_path, [])
        entries = [
            {"id": "bad-entry", "type": "lesson"},  # Missing required fields
        ]
        config = _make_config()
        result = batch_validate(entries, self.events_path, config)
        self.assertEqual(len(result.invalid), 1)
        self.assertEqual(len(result.valid), 0)

    def test_dedup_against_existing(self):
        existing = _make_valid_entry(
            entry_id="lesson-existing-aabb0001",
            title="Existing entry title",
            rule="MUST test everything",
        )
        _write_events(self.events_path, [existing])

        # New entry that's nearly identical
        new_entry = _make_valid_entry(
            entry_id="lesson-new_one-aabb0002",
            title="Existing entry title",
            rule="MUST test everything",
        )
        config = _make_config()
        result = batch_validate([new_entry], self.events_path, config)
        self.assertEqual(len(result.duplicates), 1)

    def test_cross_dedup_within_batch(self):
        _write_events(self.events_path, [])
        entry1 = _make_valid_entry(
            entry_id="lesson-first-aabb0001",
            title="Same title here",
            rule="MUST do the same thing",
        )
        entry2 = _make_valid_entry(
            entry_id="lesson-second-aabb0002",
            title="Same title here",
            rule="MUST do the same thing",
        )
        config = _make_config()
        result = batch_validate([entry1, entry2], self.events_path, config)
        # First should be valid, second should be flagged as cross-duplicate
        self.assertEqual(len(result.valid), 1)
        self.assertEqual(len(result.duplicates), 1)

    def test_mixed_batch(self):
        _write_events(self.events_path, [])
        valid = _make_valid_entry(entry_id="lesson-good-aabb0001")
        invalid = {"id": "bad", "type": "lesson"}  # Missing fields
        config = _make_config()
        result = batch_validate([valid, invalid], self.events_path, config)
        self.assertEqual(len(result.valid), 1)
        self.assertEqual(len(result.invalid), 1)
        self.assertEqual(result.total, 2)

    def test_threshold_from_config(self):
        _write_events(self.events_path, [])
        config = _make_config()
        config["automation"]["dedup_threshold"] = 0.99  # Very strict
        entry1 = _make_valid_entry(entry_id="lesson-a-aabb0001", title="Title A", rule="MUST do A")
        entry2 = _make_valid_entry(entry_id="lesson-b-aabb0002", title="Title B", rule="MUST do B")
        result = batch_validate([entry1, entry2], self.events_path, config)
        # With 0.99 threshold, these should NOT be flagged as duplicates
        self.assertEqual(len(result.valid), 2)
        self.assertEqual(len(result.duplicates), 0)


# ===========================================================================
# Test: batch_write
# ===========================================================================

class TestBatchWrite(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.events_path = self.tmpdir / ".memory" / "events.jsonl"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_writes_all_entries(self):
        entries = [
            _make_valid_entry(entry_id="lesson-a-aabb0001"),
            _make_valid_entry(entry_id="lesson-b-aabb0002"),
        ]
        result = batch_write(entries, self.events_path)
        self.assertEqual(result.written_count, 2)
        # Verify file contents
        lines = self.events_path.read_text().strip().split("\n")
        self.assertEqual(len(lines), 2)

    def test_creates_events_file(self):
        self.assertFalse(self.events_path.exists())
        entries = [_make_valid_entry()]
        result = batch_write(entries, self.events_path)
        self.assertTrue(self.events_path.exists())
        self.assertEqual(result.written_count, 1)

    def test_preserves_existing_entries(self):
        # Write initial entry
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self.events_path.write_text(
            json.dumps({"id": "existing-entry-00000001"}) + "\n"
        )
        # Append new entries
        entries = [_make_valid_entry(entry_id="lesson-new-aabb0001")]
        batch_write(entries, self.events_path)
        lines = self.events_path.read_text().strip().split("\n")
        self.assertEqual(len(lines), 2)
        # First line should be the existing entry
        first = json.loads(lines[0])
        self.assertEqual(first["id"], "existing-entry-00000001")

    def test_returns_entry_ids(self):
        entries = [
            _make_valid_entry(entry_id="lesson-a-aabb0001"),
            _make_valid_entry(entry_id="lesson-b-aabb0002"),
        ]
        result = batch_write(entries, self.events_path)
        self.assertEqual(result.entry_ids, ["lesson-a-aabb0001", "lesson-b-aabb0002"])

    def test_empty_batch(self):
        result = batch_write([], self.events_path)
        self.assertEqual(result.written_count, 0)
        self.assertFalse(self.events_path.exists())


# ===========================================================================
# Test: ScanReport dataclass
# ===========================================================================

class TestScanReport(unittest.TestCase):

    def test_default_values(self):
        report = ScanReport()
        self.assertEqual(report.documents, [])
        self.assertEqual(report.total_scanned, 0)
        self.assertEqual(report.duration_ms, 0.0)


# ===========================================================================
# Test: _extract_snippet
# ===========================================================================

class TestExtractSnippet(unittest.TestCase):

    def test_heading_and_content(self):
        from lib.scanner import _extract_snippet
        content = "# My Title\nSome content here\nMore content"
        result = _extract_snippet(content)
        self.assertIn("My Title", result)
        self.assertIn("Some content", result)

    def test_no_heading(self):
        from lib.scanner import _extract_snippet
        content = "Just plain text\nMore text"
        result = _extract_snippet(content)
        self.assertIn("Just plain text", result)

    def test_empty_content(self):
        from lib.scanner import _extract_snippet
        result = _extract_snippet("")
        self.assertEqual(result, "")

    def test_long_line_truncated(self):
        from lib.scanner import _extract_snippet
        content = "# Title\n" + "x" * 200
        result = _extract_snippet(content)
        # first_line should be truncated to 120 chars
        parts = result.split(" | ")
        if len(parts) > 1:
            self.assertLessEqual(len(parts[1]), 120)


# ===========================================================================
# Test: File size limits (B1)
# ===========================================================================

class TestFileSizeLimits(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_oversized_file_skipped(self):
        """Files larger than max_file_size_bytes should return None."""
        from lib.scanner import _build_document_info
        # Create a file larger than limit
        large_file = self.tmpdir / "large.md"
        large_file.write_text("x" * 100)  # 100 bytes

        config = {"scan": {"max_file_size_bytes": 50}}  # 50 byte limit
        result = _build_document_info(large_file, "large.md", config, {})
        self.assertIsNone(result)

    def test_normal_file_not_skipped(self):
        """Files under the limit should return DocumentInfo."""
        from lib.scanner import _build_document_info
        normal_file = self.tmpdir / "normal.md"
        normal_file.write_text("# Hello\nShort file")

        config = {"scan": {"max_file_size_bytes": 5_242_880}}
        result = _build_document_info(normal_file, "normal.md", config, {})
        self.assertIsNotNone(result)

    def test_discover_counts_oversized(self):
        """discover_documents should count skipped oversized files."""
        _create_project(self.tmpdir, {
            "docs/small.md": "# Small\nContent",
            "docs/large.md": "x" * 200,
        })
        config = _make_config()
        config["scan"]["max_file_size_bytes"] = 100
        report = discover_documents(self.tmpdir, config)
        self.assertGreaterEqual(report.skipped_oversized, 1)

    def test_default_size_limit(self):
        """Default size limit should be 5MB."""
        from lib.scanner import _MAX_FILE_SIZE_BYTES
        self.assertEqual(_MAX_FILE_SIZE_BYTES, 5_242_880)


# ===========================================================================
# Test: ScanReport skipped_oversized field
# ===========================================================================

class TestScanReportOversized(unittest.TestCase):

    def test_default_zero(self):
        report = ScanReport()
        self.assertEqual(report.skipped_oversized, 0)


if __name__ == "__main__":
    unittest.main()
