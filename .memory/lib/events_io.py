"""
EF Memory — Unified events.jsonl I/O

Single source of truth for reading events.jsonl with latest-wins semantics.
Replaces four independent JSONL parsers that existed in auto_verify, search,
sync, and generate_rules with one shared implementation.

All callers apply their own post-filters (deprecated, hard classification, etc.)
on top of the base latest-wins dict returned here.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger("efm.events_io")


def load_events_latest_wins(
    events_path: Path,
    start_line: int = 0,
    track_lines: bool = False,
    byte_offset: int = 0,
) -> Tuple[Dict[str, dict], int, int]:
    """
    Load entries from events.jsonl with latest-wins semantics.

    Args:
        events_path: Path to events.jsonl.
        start_line: Skip JSON parsing for lines before this index (0-based).
                    Ignored if ``byte_offset > 0`` (byte offset takes priority).
        track_lines: If True, each entry dict gets an ``_line`` key
                     with its 0-based line index.
        byte_offset: If > 0, seek directly to this byte position instead of
                     scanning from the beginning.  Much faster for incremental
                     sync on large files.

    Returns:
        (entries, total_lines, end_byte_offset)
        - entries: ``{entry_id: latest_entry_dict}`` (includes all entries,
          both active and deprecated — callers filter as needed).
        - total_lines: total number of lines in the file (including blank).
        - end_byte_offset: byte position at end of file, for cursor storage.
    """
    entries: Dict[str, dict] = {}
    total_lines = 0
    end_offset = 0

    if not events_path.exists():
        return entries, 0, 0

    try:
        with open(events_path, "r", encoding="utf-8") as f:
            if byte_offset > 0:
                # Fast path: seek directly to unprocessed content
                f.seek(byte_offset)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        entry_id = entry.get("id")
                        if entry_id:
                            entries[entry_id] = entry
                    except json.JSONDecodeError as e:
                        logger.debug("Skipping invalid JSON: %s", e)
                # Count total lines (needed for backward compat)
                f.seek(0)
                total_lines = sum(1 for _ in f)
            else:
                # Standard path: scan from beginning
                for i, line in enumerate(f):
                    total_lines = i + 1
                    line = line.strip()
                    if not line:
                        continue
                    if i < start_line:
                        continue
                    try:
                        entry = json.loads(line)
                        entry_id = entry.get("id")
                        if entry_id:
                            if track_lines:
                                entry["_line"] = i
                            entries[entry_id] = entry
                    except json.JSONDecodeError as e:
                        logger.debug("Skipping invalid JSON at line %d: %s", i + 1, e)

            end_offset = f.seek(0, 2)  # Seek to end to get byte offset

    except OSError:
        pass

    return entries, total_lines, end_offset
