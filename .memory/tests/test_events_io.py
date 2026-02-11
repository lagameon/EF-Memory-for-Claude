"""
EF Memory — Tests for events_io module

Comprehensive tests for load_events_latest_wins() covering standard path,
byte-offset path, error handling, and edge cases.

Run:
    cd .memory/tests && python3 -m pytest test_events_io.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure .memory/ is on the import path so 'lib' is importable
_MEMORY_DIR = Path(__file__).resolve().parent.parent
if str(_MEMORY_DIR) not in sys.path:
    sys.path.insert(0, str(_MEMORY_DIR))

from lib.events_io import load_events_latest_wins


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(entry_id, title="Test entry", **kwargs):
    """Create a minimal valid entry dict."""
    entry = {"id": entry_id, "type": "lesson", "title": title}
    entry.update(kwargs)
    return entry


def _write_jsonl(path, lines):
    """Write a list of strings (raw lines) to a file."""
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def _write_entries(path, entries):
    """Write a list of entry dicts as JSONL."""
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Tests — Basic loading
# ---------------------------------------------------------------------------

class TestLoadEventsBasic:
    """Tests for basic load_events_latest_wins behavior."""

    def test_load_empty_file(self, tmp_path):
        """Empty events.jsonl returns ({}, 0, 0)."""
        events_file = tmp_path / "events.jsonl"
        events_file.write_text("")

        entries, total_lines, end_offset = load_events_latest_wins(events_file)

        assert entries == {}
        assert total_lines == 0
        # An empty file has 0 bytes
        assert end_offset == 0

    def test_load_nonexistent_file(self, tmp_path):
        """Missing file returns ({}, 0, 0)."""
        missing = tmp_path / "does_not_exist.jsonl"

        entries, total_lines, end_offset = load_events_latest_wins(missing)

        assert entries == {}
        assert total_lines == 0
        assert end_offset == 0

    def test_load_single_entry(self, tmp_path):
        """One valid JSON line is loaded correctly."""
        events_file = tmp_path / "events.jsonl"
        entry = _make_entry("entry-001", title="First entry")
        _write_entries(events_file, [entry])

        entries, total_lines, end_offset = load_events_latest_wins(events_file)

        assert len(entries) == 1
        assert "entry-001" in entries
        assert entries["entry-001"]["title"] == "First entry"
        assert total_lines == 1
        assert end_offset > 0

    def test_load_multiple_entries(self, tmp_path):
        """Three entries with unique IDs are all returned."""
        events_file = tmp_path / "events.jsonl"
        e1 = _make_entry("a1", title="Alpha")
        e2 = _make_entry("b2", title="Bravo")
        e3 = _make_entry("c3", title="Charlie")
        _write_entries(events_file, [e1, e2, e3])

        entries, total_lines, end_offset = load_events_latest_wins(events_file)

        assert len(entries) == 3
        assert set(entries.keys()) == {"a1", "b2", "c3"}
        assert total_lines == 3


# ---------------------------------------------------------------------------
# Tests — Latest-wins semantics
# ---------------------------------------------------------------------------

class TestLatestWins:
    """Tests for duplicate ID handling (last entry wins)."""

    def test_latest_wins_semantics(self, tmp_path):
        """Duplicate IDs: the last occurrence wins."""
        events_file = tmp_path / "events.jsonl"
        e1 = _make_entry("dup-id", title="Version 1")
        e2 = _make_entry("dup-id", title="Version 2")
        e3 = _make_entry("dup-id", title="Version 3 (latest)")
        _write_entries(events_file, [e1, e2, e3])

        entries, total_lines, end_offset = load_events_latest_wins(events_file)

        assert len(entries) == 1
        assert entries["dup-id"]["title"] == "Version 3 (latest)"
        assert total_lines == 3

    def test_deprecated_entries_included(self, tmp_path):
        """Deprecated entries are returned (callers filter)."""
        events_file = tmp_path / "events.jsonl"
        active = _make_entry("active-1", title="Active", deprecated=False)
        deprecated = _make_entry("dep-1", title="Deprecated", deprecated=True)
        _write_entries(events_file, [active, deprecated])

        entries, total_lines, end_offset = load_events_latest_wins(events_file)

        assert len(entries) == 2
        assert "dep-1" in entries
        assert entries["dep-1"]["deprecated"] is True


# ---------------------------------------------------------------------------
# Tests — start_line and track_lines
# ---------------------------------------------------------------------------

class TestStartLineAndTrackLines:
    """Tests for start_line skipping and track_lines metadata."""

    def test_start_line_skips_parsing(self, tmp_path):
        """start_line=2 skips first 2 lines (lines 0 and 1)."""
        events_file = tmp_path / "events.jsonl"
        e1 = _make_entry("skip-1", title="Should be skipped")
        e2 = _make_entry("skip-2", title="Also skipped")
        e3 = _make_entry("keep-3", title="Kept")
        e4 = _make_entry("keep-4", title="Also kept")
        _write_entries(events_file, [e1, e2, e3, e4])

        entries, total_lines, end_offset = load_events_latest_wins(
            events_file, start_line=2
        )

        assert len(entries) == 2
        assert "skip-1" not in entries
        assert "skip-2" not in entries
        assert "keep-3" in entries
        assert "keep-4" in entries
        # total_lines still reflects the full file
        assert total_lines == 4

    def test_track_lines_adds_meta(self, tmp_path):
        """track_lines=True adds _line key with 0-based line index."""
        events_file = tmp_path / "events.jsonl"
        e1 = _make_entry("line-0")
        e2 = _make_entry("line-1")
        e3 = _make_entry("line-2")
        _write_entries(events_file, [e1, e2, e3])

        entries, total_lines, end_offset = load_events_latest_wins(
            events_file, track_lines=True
        )

        assert entries["line-0"]["_line"] == 0
        assert entries["line-1"]["_line"] == 1
        assert entries["line-2"]["_line"] == 2


# ---------------------------------------------------------------------------
# Tests — Byte offset path
# ---------------------------------------------------------------------------

class TestByteOffset:
    """Tests for byte_offset seeking behavior."""

    def test_byte_offset_reads_from_position(self, tmp_path):
        """byte_offset seeks correctly and reads only new entries."""
        events_file = tmp_path / "events.jsonl"
        e1 = _make_entry("old-1", title="Already synced")
        e2 = _make_entry("old-2", title="Already synced too")

        # Write initial entries
        _write_entries(events_file, [e1, e2])
        # Record the byte offset after initial entries
        initial_size = events_file.stat().st_size

        # Append new entries
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(_make_entry("new-3", title="New entry")) + "\n")
            f.write(json.dumps(_make_entry("new-4", title="Another new")) + "\n")

        entries, total_lines, end_offset = load_events_latest_wins(
            events_file, byte_offset=initial_size
        )

        # Should only see the new entries
        assert len(entries) == 2
        assert "new-3" in entries
        assert "new-4" in entries
        assert "old-1" not in entries
        assert "old-2" not in entries

    def test_byte_offset_total_lines_zero(self, tmp_path):
        """total_lines=0 in byte-offset mode (verifies the PERF fix)."""
        events_file = tmp_path / "events.jsonl"
        e1 = _make_entry("a")
        e2 = _make_entry("b")
        e3 = _make_entry("c")
        _write_entries(events_file, [e1, e2, e3])

        # Read from beginning as byte_offset > 0 (offset=1 to trigger byte path)
        # Use actual beginning to read all entries via byte path
        entries, total_lines, end_offset = load_events_latest_wins(
            events_file, byte_offset=1
        )

        # The critical assertion: total_lines must be 0 in byte-offset mode
        assert total_lines == 0
        # end_offset should still reflect file size
        assert end_offset == events_file.stat().st_size


# ---------------------------------------------------------------------------
# Tests — Invalid / malformed data handling
# ---------------------------------------------------------------------------

class TestInvalidData:
    """Tests for handling malformed JSON and edge cases."""

    def test_invalid_json_skipped(self, tmp_path):
        """Malformed JSON lines are skipped without error."""
        events_file = tmp_path / "events.jsonl"
        lines = [
            json.dumps(_make_entry("valid-1")),
            "this is not json {{{",
            json.dumps(_make_entry("valid-2")),
        ]
        _write_jsonl(events_file, lines)

        entries, total_lines, end_offset = load_events_latest_wins(events_file)

        assert len(entries) == 2
        assert "valid-1" in entries
        assert "valid-2" in entries
        assert total_lines == 3

    def test_blank_lines_skipped(self, tmp_path):
        """Empty/whitespace lines are ignored."""
        events_file = tmp_path / "events.jsonl"
        lines = [
            json.dumps(_make_entry("e1")),
            "",
            "   ",
            json.dumps(_make_entry("e2")),
        ]
        _write_jsonl(events_file, lines)

        entries, total_lines, end_offset = load_events_latest_wins(events_file)

        assert len(entries) == 2
        assert "e1" in entries
        assert "e2" in entries
        # total_lines counts all lines including blank
        assert total_lines == 4

    def test_entry_without_id_skipped(self, tmp_path):
        """JSON without 'id' key is skipped."""
        events_file = tmp_path / "events.jsonl"
        lines = [
            json.dumps({"id": "has-id", "title": "OK"}),
            json.dumps({"title": "No id field", "type": "lesson"}),
            json.dumps({"id": "also-has-id", "title": "Also OK"}),
        ]
        _write_jsonl(events_file, lines)

        entries, total_lines, end_offset = load_events_latest_wins(events_file)

        assert len(entries) == 2
        assert "has-id" in entries
        assert "also-has-id" in entries

    def test_mixed_valid_invalid(self, tmp_path):
        """Interleaved good/bad JSON: valid entries survive."""
        events_file = tmp_path / "events.jsonl"
        lines = [
            json.dumps(_make_entry("ok-1")),
            "not json at all",
            "",
            json.dumps({"no_id": True}),
            json.dumps(_make_entry("ok-2")),
            "{broken json",
            json.dumps(_make_entry("ok-3")),
        ]
        _write_jsonl(events_file, lines)

        entries, total_lines, end_offset = load_events_latest_wins(events_file)

        assert len(entries) == 3
        assert set(entries.keys()) == {"ok-1", "ok-2", "ok-3"}
        assert total_lines == 7


# ---------------------------------------------------------------------------
# Tests — End byte offset
# ---------------------------------------------------------------------------

class TestEndByteOffset:
    """Tests for correct end_byte_offset reporting."""

    def test_end_byte_offset_correct(self, tmp_path):
        """Returned offset matches file size."""
        events_file = tmp_path / "events.jsonl"
        _write_entries(events_file, [
            _make_entry("x1"),
            _make_entry("x2"),
            _make_entry("x3"),
        ])
        expected_size = events_file.stat().st_size

        entries, total_lines, end_offset = load_events_latest_wins(events_file)

        assert end_offset == expected_size


# ---------------------------------------------------------------------------
# Tests — Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Tests for OSError / permission error handling."""

    def test_oserror_returns_empty(self, tmp_path):
        """File permission error (OSError) returns empty tuple."""
        events_file = tmp_path / "events.jsonl"
        # Create the file so exists() returns True
        events_file.write_text(json.dumps(_make_entry("e1")) + "\n")

        # Mock open to raise OSError after the exists() check passes
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            entries, total_lines, end_offset = load_events_latest_wins(events_file)

        assert entries == {}
        assert total_lines == 0
        assert end_offset == 0


# ---------------------------------------------------------------------------
# Tests — Large file
# ---------------------------------------------------------------------------

class TestLargeFile:
    """Tests for larger file handling."""

    def test_large_file_line_count(self, tmp_path):
        """100+ entries: verify total_lines in standard path."""
        events_file = tmp_path / "events.jsonl"
        count = 150
        entries_list = [_make_entry(f"entry-{i:04d}") for i in range(count)]
        _write_entries(events_file, entries_list)

        entries, total_lines, end_offset = load_events_latest_wins(events_file)

        assert len(entries) == count
        assert total_lines == count
        assert end_offset > 0


# ---------------------------------------------------------------------------
# Tests — Incremental sync simulation
# ---------------------------------------------------------------------------

class TestIncrementalSync:
    """Tests simulating real incremental sync workflow."""

    def test_byte_offset_incremental(self, tmp_path):
        """Two calls simulate incremental sync: first full, then from offset."""
        events_file = tmp_path / "events.jsonl"

        # Phase 1: Write initial entries and do a full read
        initial_entries = [
            _make_entry("phase1-a", title="Initial A"),
            _make_entry("phase1-b", title="Initial B"),
        ]
        _write_entries(events_file, initial_entries)

        entries1, total_lines1, offset1 = load_events_latest_wins(events_file)

        assert len(entries1) == 2
        assert total_lines1 == 2
        assert offset1 == events_file.stat().st_size

        # Phase 2: Append new entries
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(_make_entry("phase2-c", title="New C")) + "\n")
            f.write(json.dumps(_make_entry("phase2-d", title="New D")) + "\n")
            f.write(json.dumps(_make_entry("phase2-e", title="New E")) + "\n")

        # Read only new entries using the saved offset
        entries2, total_lines2, offset2 = load_events_latest_wins(
            events_file, byte_offset=offset1
        )

        # Should only get the 3 new entries
        assert len(entries2) == 3
        assert set(entries2.keys()) == {"phase2-c", "phase2-d", "phase2-e"}
        # total_lines is 0 in byte-offset mode (PERF fix)
        assert total_lines2 == 0
        # offset2 should be the new file size
        assert offset2 == events_file.stat().st_size
        # The new offset should be larger than the old one
        assert offset2 > offset1
