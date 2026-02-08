#!/usr/bin/env python3
"""
EF Memory — Compaction CLI (M11)

Compact events.jsonl: resolve latest-wins, remove deprecated, archive by quarter.

Usage:
    python3 .memory/scripts/compact_cli.py              # Run compaction
    python3 .memory/scripts/compact_cli.py --dry-run    # Show what would happen
    python3 .memory/scripts/compact_cli.py --stats      # Show waste stats only
    python3 .memory/scripts/compact_cli.py --help       # Show help
"""

import json
import sys
from pathlib import Path

# Add .memory/ to import path
_SCRIPT_DIR = Path(__file__).resolve().parent
_MEMORY_DIR = _SCRIPT_DIR.parent
_PROJECT_ROOT = _MEMORY_DIR.parent
sys.path.insert(0, str(_MEMORY_DIR))

from lib.compaction import compact, get_compaction_stats


def _parse_args(argv: list) -> dict:
    """Simple argument parser."""
    args = {
        "dry_run": False,
        "stats": False,
        "help": False,
    }
    for arg in argv[1:]:
        if arg == "--dry-run":
            args["dry_run"] = True
        elif arg == "--stats":
            args["stats"] = True
        elif arg in ("--help", "-h"):
            args["help"] = True
    return args


def _load_config() -> dict:
    config_path = _MEMORY_DIR / "config.json"
    try:
        return json.loads(config_path.read_text())
    except Exception:
        return {}


def _print_stats(stats) -> None:
    """Print compaction statistics."""
    print(f"events.jsonl statistics:")
    print(f"  Total lines:       {stats.total_lines}")
    print(f"  Unique entries:    {stats.unique_entries}")
    print(f"  Active entries:    {stats.active_entries}")
    print(f"  Deprecated:        {stats.deprecated_entries}")
    print(f"  Superseded lines:  {stats.superseded_lines}")
    print(f"  Waste ratio:       {stats.waste_ratio:.2f}x")
    print(f"  Suggest compact:   {'yes' if stats.suggest_compact else 'no'}")


def main():
    args = _parse_args(sys.argv)

    if args["help"]:
        print(__doc__)
        sys.exit(0)

    config = _load_config()
    events_path = _MEMORY_DIR / "events.jsonl"
    compact_config = config.get("compaction", {})
    threshold = compact_config.get("auto_suggest_threshold", 2.0)

    # Stats mode
    if args["stats"]:
        stats = get_compaction_stats(events_path, threshold=threshold)
        _print_stats(stats)
        sys.exit(0)

    # Dry-run mode
    if args["dry_run"]:
        stats = get_compaction_stats(events_path, threshold=threshold)
        _print_stats(stats)
        print()
        if stats.waste_ratio <= 1.0:
            print("No compaction needed — file is already clean.")
        else:
            removable = stats.total_lines - stats.active_entries
            print(f"Compaction would:")
            print(f"  Keep {stats.active_entries} active entries")
            print(f"  Archive {removable} lines ({stats.deprecated_entries} deprecated + {stats.superseded_lines} superseded)")
            print(f"  Reduce file from {stats.total_lines} to {stats.active_entries} lines")
        sys.exit(0)

    # Run compaction
    stats = get_compaction_stats(events_path, threshold=threshold)
    if stats.waste_ratio <= 1.0:
        print("events.jsonl is already compact — nothing to do.")
        sys.exit(0)

    archive_rel = compact_config.get("archive_dir", ".memory/archive")
    archive_dir = _PROJECT_ROOT / archive_rel

    print(f"Compacting events.jsonl ({stats.total_lines} lines, {stats.waste_ratio:.1f}x waste)...")
    report = compact(events_path, archive_dir, config)

    print(f"Done in {report.duration_ms:.0f}ms:")
    print(f"  Lines:    {report.lines_before} → {report.lines_after}")
    print(f"  Kept:     {report.entries_kept} active entries")
    print(f"  Archived: {report.lines_archived} lines to {report.quarters_touched}")
    if report.archive_dir:
        print(f"  Archive:  {report.archive_dir}")


if __name__ == "__main__":
    main()
