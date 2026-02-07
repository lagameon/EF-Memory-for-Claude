#!/usr/bin/env python3
"""
EF Memory V3 — Working Memory CLI

Manage working memory sessions for multi-step tasks.

Usage:
    python3 .memory/scripts/working_memory_cli.py start "task description"
    python3 .memory/scripts/working_memory_cli.py resume
    python3 .memory/scripts/working_memory_cli.py status
    python3 .memory/scripts/working_memory_cli.py harvest
    python3 .memory/scripts/working_memory_cli.py clear
    python3 .memory/scripts/working_memory_cli.py read-plan
    python3 .memory/scripts/working_memory_cli.py --help
"""

import json
import logging
import sys
from pathlib import Path

# Add .memory/ to import path
_SCRIPT_DIR = Path(__file__).resolve().parent
_MEMORY_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_MEMORY_DIR))

from lib.working_memory import (
    clear_session,
    get_session_status,
    harvest_session,
    read_plan_summary,
    resume_session,
    start_session,
)


def _parse_args(argv: list) -> dict:
    """Simple argument parser."""
    args = {
        "command": None,
        "task_description": None,
        "help": False,
    }

    if not argv:
        args["help"] = True
        return args

    for a in argv:
        if a in ("--help", "-h"):
            args["help"] = True
            return args

    cmd = argv[0]
    if cmd in ("start", "resume", "status", "harvest", "clear", "read-plan"):
        args["command"] = cmd
    else:
        print(f"ERROR: Unknown command: {cmd}")
        sys.exit(1)

    if cmd == "start":
        if len(argv) < 2:
            print("ERROR: 'start' requires a task description")
            print("Usage: python3 .memory/scripts/working_memory_cli.py start \"task description\"")
            sys.exit(1)
        args["task_description"] = " ".join(argv[1:])

    return args


def _print_start(report):
    """Print session start report."""
    if report.already_exists:
        print("Working memory session already exists.")
        print("Use 'resume' to continue or 'clear' to start fresh.")
        return

    print("Working memory session started")
    print(f"  Task: {report.task_description}")
    print(f"  Directory: {report.working_dir}")
    print(f"  Files created: {', '.join(report.files_created)}")
    if report.prefill_count > 0:
        print(f"  Prefilled: {report.prefill_count} relevant memories into findings.md")
        for entry in report.prefill_entries:
            severity = f"/{entry.severity}" if entry.severity else ""
            print(f"    [{entry.classification}{severity}] {entry.title[:60]} (score: {entry.score:.2f})")
    else:
        print("  Prefilled: 0 (no matching memories found)")
    print(f"\n  Duration: {report.duration_ms:.0f}ms")


def _print_resume(report):
    """Print session resume report."""
    if report is None:
        print("No active working memory session.")
        print("Use 'start \"task description\"' to begin one.")
        return

    print("Working memory session resumed")
    print(f"  Task: {report.task_description}")
    print(f"  Current phase: {report.current_phase}")
    print(f"  Progress: {report.phases_done}/{report.phases_total} phases done")
    if report.findings_count > 0:
        print(f"  Findings: {report.findings_count} discoveries recorded")
    if report.last_progress_line:
        print(f"  Last action: {report.last_progress_line[:80]}")
    print(f"\n  Duration: {report.duration_ms:.0f}ms")


def _print_status(status):
    """Print session status."""
    if not status.active:
        print("No active working memory session.")
        return

    print("Working memory session status")
    print(f"  Task: {status.task_description}")
    print(f"  Phases: {status.phases_done}/{status.phases_total} done")
    print(f"  Findings: {status.findings_count} lines")
    print(f"  Progress: {status.progress_lines} actions logged")
    print(f"  Created: {status.created_at}")
    print(f"  Last modified: {status.last_modified}")


def _print_harvest(report):
    """Print harvest report."""
    if not report.candidates:
        print("No memory candidates found in working files.")
        if not report.findings_scanned and not report.progress_scanned:
            print("  (No working memory files found — start a session first)")
        return

    print(f"Found {len(report.candidates)} memory candidate(s):\n")
    for i, c in enumerate(report.candidates, 1):
        print(f"  [{i}] [{c.suggested_type}] {c.title}")
        if c.rule:
            print(f"      Rule: {c.rule[:80]}")
        if c.implication:
            print(f"      Implication: {c.implication[:80]}")
        print(f"      Reason: {c.extraction_reason}")
        print(f"      Source: {c.source_hint}")
        print()

    print(f"  Duration: {report.duration_ms:.0f}ms")
    print("\nUse /memory-save to persist candidates to project memory.")


def main():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    args = _parse_args(sys.argv[1:])

    if args["help"]:
        print(__doc__.strip())
        sys.exit(0)

    # Resolve paths
    project_root = _MEMORY_DIR.parent
    events_path = _MEMORY_DIR / "events.jsonl"

    # Load config
    config_path = _MEMORY_DIR / "config.json"
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Working directory from config
    v3_config = config.get("v3", {})
    working_dir_rel = v3_config.get("working_memory_dir", ".memory/working")
    working_dir = project_root / working_dir_rel

    cmd = args["command"]

    if cmd == "start":
        report = start_session(
            task_description=args["task_description"],
            events_path=events_path,
            working_dir=working_dir,
            config=config,
            project_root=project_root,
        )
        _print_start(report)

    elif cmd == "resume":
        report = resume_session(working_dir)
        _print_resume(report)

    elif cmd == "status":
        status = get_session_status(working_dir)
        _print_status(status)

    elif cmd == "harvest":
        report = harvest_session(working_dir, events_path, config)
        _print_harvest(report)

    elif cmd == "clear":
        if clear_session(working_dir):
            print("Working memory session cleared.")
        else:
            print("No active session to clear.")

    elif cmd == "read-plan":
        summary = read_plan_summary(working_dir)
        if summary:
            print(summary)
        else:
            print("No active working memory session.")


if __name__ == "__main__":
    main()
