#!/usr/bin/env python3
"""
EF Memory V3 — Project Init CLI

Initialize EF Memory auto-startup for a project. Generates CLAUDE.md,
.claude/rules/, hooks.json, and settings.local.json.

Usage:
    python3 .memory/scripts/init_cli.py                    # Init current project
    python3 .memory/scripts/init_cli.py --dry-run           # Preview without writing
    python3 .memory/scripts/init_cli.py --force             # Overwrite existing EF Memory sections
    python3 .memory/scripts/init_cli.py --target /path/to   # Init a different project
    python3 .memory/scripts/init_cli.py --help              # Show help
"""

import json
import logging
import sys
from pathlib import Path

# Add .memory/ to import path
_SCRIPT_DIR = Path(__file__).resolve().parent
_MEMORY_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_MEMORY_DIR))

from lib.init import run_init


def _parse_args(argv: list) -> dict:
    """Simple argument parser."""
    args = {
        "dry_run": False,
        "force": False,
        "target": None,
        "help": False,
    }
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--help", "-h"):
            args["help"] = True
        elif arg == "--dry-run":
            args["dry_run"] = True
        elif arg == "--force":
            args["force"] = True
        elif arg == "--target":
            if i + 1 < len(argv):
                args["target"] = argv[i + 1]
                i += 1
            else:
                print("ERROR: --target requires a path argument")
                sys.exit(1)
        elif arg.startswith("--target="):
            args["target"] = arg.split("=", 1)[1]
        elif arg.startswith("--"):
            print(f"ERROR: Unknown option: {arg}")
            sys.exit(1)
        i += 1
    return args


def _print_report(report):
    """Print the init report."""
    mode = "[DRY RUN] " if report.dry_run else ""

    if report.files_created:
        print(f"\n{mode}Created:")
        for f in report.files_created:
            print(f"  + {f}")

    if report.files_merged:
        print(f"\n{mode}Merged:")
        for f in report.files_merged:
            print(f"  ~ {f}")

    if report.files_skipped:
        print(f"\n{mode}Skipped (already exists):")
        for f in report.files_skipped:
            print(f"  - {f}")

    if report.warnings:
        print(f"\nWarnings:")
        for w in report.warnings:
            print(f"  ! {w}")

    if report.suggestions:
        print(f"\nSuggestions:")
        for s in report.suggestions:
            print(f"  > {s}")

    total = len(report.files_created) + len(report.files_merged) + len(report.files_skipped)
    print(f"\n{mode}Done ({total} files processed, {report.duration_ms:.0f}ms)")


def main():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    args = _parse_args(sys.argv[1:])

    if args["help"]:
        print(__doc__.strip())
        sys.exit(0)

    # Resolve project root
    if args["target"]:
        project_root = Path(args["target"]).resolve()
        if not project_root.is_dir():
            print(f"ERROR: Target directory does not exist: {project_root}")
            sys.exit(1)
    else:
        project_root = _MEMORY_DIR.parent

    # Load config
    config_path = _MEMORY_DIR / "config.json"
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(f"WARNING: Could not parse config.json: {exc}")

    # Run init
    print(f"EF Memory Init — {project_root}")
    if args["dry_run"]:
        print("(dry run — no files will be written)")

    report = run_init(
        project_root=project_root,
        config=config,
        force=args["force"],
        dry_run=args["dry_run"],
    )

    _print_report(report)


if __name__ == "__main__":
    main()
