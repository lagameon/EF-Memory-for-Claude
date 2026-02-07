#!/usr/bin/env python3
"""
EF Memory V3 — Document Scanner CLI

Discover, validate, and commit memory entries from batch document scanning.

Usage:
    python3 .memory/scripts/scan_cli.py discover                    # Human-readable table
    python3 .memory/scripts/scan_cli.py discover --json             # JSON output for Claude
    python3 .memory/scripts/scan_cli.py discover --pattern "**/*.md"
    python3 .memory/scripts/scan_cli.py validate                    # Read entries from stdin
    python3 .memory/scripts/scan_cli.py commit                      # Read entries from stdin, write + pipeline
    python3 .memory/scripts/scan_cli.py --help
"""

import json
import logging
import sys
from pathlib import Path

# Add .memory/ to import path
_SCRIPT_DIR = Path(__file__).resolve().parent
_MEMORY_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_MEMORY_DIR))

from lib.scanner import (
    batch_validate,
    batch_write,
    discover_documents,
)


def _parse_args(argv: list) -> dict:
    """Simple argument parser."""
    args = {
        "command": None,    # discover, validate, commit
        "json": False,
        "pattern": None,
        "help": False,
    }

    positionals = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--help", "-h"):
            args["help"] = True
        elif arg == "--json":
            args["json"] = True
        elif arg == "--pattern":
            if i + 1 < len(argv):
                args["pattern"] = argv[i + 1]
                i += 1
            else:
                print("ERROR: --pattern requires a value")
                sys.exit(1)
        elif arg.startswith("--pattern="):
            args["pattern"] = arg.split("=", 1)[1]
        elif arg.startswith("--"):
            print(f"ERROR: Unknown option: {arg}")
            sys.exit(1)
        else:
            positionals.append(arg)
        i += 1

    if positionals:
        args["command"] = positionals[0]

    return args


def _load_config() -> dict:
    """Load EF Memory config."""
    config_path = _MEMORY_DIR / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(f"WARNING: Could not parse config.json: {exc}", file=sys.stderr)
    return {}


def _resolve_project_root() -> Path:
    """Resolve project root (parent of .memory/)."""
    return _MEMORY_DIR.parent


def _read_entries_from_stdin() -> list:
    """Read JSON array of entries from stdin."""
    try:
        data = sys.stdin.read()
        entries = json.loads(data)
        if not isinstance(entries, list):
            print("ERROR: Expected JSON array of entries on stdin", file=sys.stderr)
            sys.exit(1)
        return entries
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON on stdin: {e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_discover(args: dict) -> None:
    """Discover candidate documents."""
    config = _load_config()
    project_root = _resolve_project_root()

    report = discover_documents(project_root, config, pattern=args.get("pattern"))

    if args.get("json"):
        # JSON output for Claude to parse
        output = {
            "total_scanned": report.total_scanned,
            "total_excluded": report.total_excluded,
            "duration_ms": round(report.duration_ms, 1),
            "documents": [
                {
                    "rel_path": d.rel_path,
                    "size_bytes": d.size_bytes,
                    "line_count": d.line_count,
                    "doc_type": d.doc_type,
                    "relevance_score": d.relevance_score,
                    "snippet": d.snippet,
                    "already_imported": d.already_imported,
                    "import_count": d.import_count,
                }
                for d in report.documents
            ],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        # Human-readable table
        print(f"\nEF Memory — Document Scanner")
        print(f"Project: {project_root}")
        print(f"Scanned: {report.total_scanned} files ({report.total_excluded} excluded)")
        print(f"Duration: {report.duration_ms:.0f}ms\n")

        if not report.documents:
            print("No candidate documents found.")
            return

        # Table header
        print(f"  {'#':>3}  {'Score':>5}  {'Path':<45}  {'Type':<6}  {'Status'}")
        print(f"  {'---':>3}  {'-----':>5}  {'-'*45}  {'------':<6}  {'------'}")

        for i, d in enumerate(report.documents, 1):
            status = f"{d.import_count} entries" if d.already_imported else "New"
            print(f"  {i:>3}  {d.relevance_score:>5.2f}  {d.rel_path:<45}  {d.doc_type:<6}  {status}")

        print(f"\nTotal: {len(report.documents)} documents")


def cmd_validate(args: dict) -> None:
    """Validate entries from stdin."""
    entries = _read_entries_from_stdin()
    config = _load_config()
    project_root = _resolve_project_root()
    events_path = project_root / ".memory" / "events.jsonl"

    result = batch_validate(entries, events_path, config)

    output = {
        "total": result.total,
        "valid_count": len(result.valid),
        "duplicate_count": len(result.duplicates),
        "invalid_count": len(result.invalid),
        "duration_ms": round(result.duration_ms, 1),
        "valid": result.valid,
        "duplicates": [
            {
                "entry": entry,
                "similar_to": [
                    {"id": eid, "similarity": sim}
                    for eid, sim in dedup.similar_entries
                ],
            }
            for entry, dedup in result.duplicates
        ],
        "invalid": [
            {
                "entry": entry,
                "errors": val.errors,
                "warnings": val.warnings,
            }
            for entry, val in result.invalid
        ],
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


def cmd_commit(args: dict) -> None:
    """Write entries from stdin and run pipeline."""
    entries = _read_entries_from_stdin()
    config = _load_config()
    project_root = _resolve_project_root()
    events_path = project_root / ".memory" / "events.jsonl"

    # Write entries
    write_result = batch_write(entries, events_path)

    # Run pipeline
    pipeline_report = None
    if write_result.written_count > 0:
        try:
            from lib.auto_sync import run_pipeline
            pipeline_steps = config.get("automation", {}).get(
                "pipeline_steps", ["sync_embeddings", "generate_rules"]
            )
            pipeline_report = run_pipeline(
                events_path=events_path,
                config=config,
                project_root=project_root,
                steps=pipeline_steps,
            )
        except Exception as e:
            print(f"WARNING: Pipeline failed: {e}", file=sys.stderr)

    output = {
        "written_count": write_result.written_count,
        "entry_ids": write_result.entry_ids,
        "errors": write_result.errors,
        "pipeline": None,
    }

    if pipeline_report:
        output["pipeline"] = {
            "steps_run": pipeline_report.steps_run,
            "steps_succeeded": pipeline_report.steps_succeeded,
            "steps_failed": pipeline_report.steps_failed,
        }

    print(json.dumps(output, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    args = _parse_args(sys.argv[1:])

    if args["help"] or not args["command"]:
        print(__doc__.strip())
        sys.exit(0)

    command = args["command"]

    if command == "discover":
        cmd_discover(args)
    elif command == "validate":
        cmd_validate(args)
    elif command == "commit":
        cmd_commit(args)
    else:
        print(f"ERROR: Unknown command: {command}")
        print("Available: discover, validate, commit")
        sys.exit(1)


if __name__ == "__main__":
    main()
