#!/usr/bin/env python3
"""
EF Memory — Stop Hook (Session Harvest + Conversation Scan)

When Claude finishes responding:

1. If an active working memory session exists:
   - v3.auto_harvest_on_stop = true: auto-harvest → events.jsonl → clear
   - v3.auto_harvest_on_stop = false: block with reminder

2. If NO session exists (normal conversation):
   - v3.auto_draft_from_conversation = true: scan transcript for patterns
     → create drafts in .memory/drafts/ → remind user to review
   - v3.auto_draft_from_conversation = false: exit silently

Runs only once per session (via the 'once' hook config flag).
Checks stop_hook_active to prevent infinite loops.
"""

import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_MEMORY_DIR = _SCRIPT_DIR.parent
_PROJECT_ROOT = _MEMORY_DIR.parent


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        sys.exit(0)

    # Prevent infinite loops: if this hook already fired, let Claude stop
    if input_data.get("stop_hook_active", False):
        sys.exit(0)

    # Load config
    config_path = _MEMORY_DIR / "config.json"
    try:
        config = json.loads(config_path.read_text())
    except Exception:
        config = {}

    v3_config = config.get("v3", {})
    working_dir_rel = v3_config.get("working_memory_dir", ".memory/working")
    working_dir = _PROJECT_ROOT / working_dir_rel
    findings_path = working_dir / "findings.md"
    progress_path = working_dir / "progress.md"

    has_session = findings_path.exists() or progress_path.exists()
    if not has_session:
        # No active working memory session — try scanning conversation
        auto_draft = v3_config.get("auto_draft_from_conversation", True)
        transcript_path = input_data.get("transcript_path")
        if not auto_draft or not transcript_path:
            sys.exit(0)

        try:
            sys.path.insert(0, str(_MEMORY_DIR))
            from lib.transcript_scanner import scan_conversation_for_drafts

            drafts_dir = _MEMORY_DIR / "drafts"
            report = scan_conversation_for_drafts(
                Path(transcript_path).expanduser(),
                drafts_dir,
                _PROJECT_ROOT,
                config,
            )
            if report["drafts_created"] > 0:
                type_summary = ", ".join(
                    f"{t} ({n})" for t, n in report["draft_types"].items()
                )
                result = {
                    "additionalContext": (
                        f"[EF Memory] Conversation scan found "
                        f"{report['candidates_found']} memory candidates "
                        f"→ saved {report['drafts_created']} drafts.\n"
                        f"  Types: {type_summary}\n"
                        f"  Review with: /memory-save (review pending drafts)\n"
                        f"  Location: .memory/drafts/\n"
                        f"No files were modified (events.jsonl unchanged). "
                        f"Drafts require your approval."
                    )
                }
                print(json.dumps(result))
        except Exception:
            pass  # Never block stopping on scan failure

        sys.exit(0)

    auto_harvest = v3_config.get("auto_harvest_on_stop", True)

    if auto_harvest:
        # Full automation: harvest → convert → write → pipeline → clear
        try:
            sys.path.insert(0, str(_MEMORY_DIR))
            from lib.working_memory import auto_harvest_and_persist

            events_path = _MEMORY_DIR / "events.jsonl"
            report = auto_harvest_and_persist(
                working_dir=working_dir,
                events_path=events_path,
                project_root=_PROJECT_ROOT,
                config=config,
                run_pipeline_after=True,
            )

            lines = ["[EF Memory] Auto-harvested working session:"]
            lines.append(f"  Candidates found: {report['candidates_found']}")
            lines.append(f"  Entries written: {report['entries_written']}")
            if report["entries_skipped"]:
                lines.append(f"  Entries skipped: {report['entries_skipped']}")
            lines.append(f"  Pipeline run: {'yes' if report['pipeline_run'] else 'no'}")
            lines.append(f"  Session cleared: {'yes' if report['session_cleared'] else 'no'}")
            if report["errors"]:
                lines.append(f"  Errors: {'; '.join(report['errors'])}")

            result = {"additionalContext": "\n".join(lines)}
            print(json.dumps(result))

        except Exception as e:
            # On failure, fall back to block + remind
            result = {
                "decision": "block",
                "reason": f"[EF Memory] Auto-harvest failed: {e}. Consider /memory-save manually.",
            }
            print(json.dumps(result))
    else:
        # Old behavior: block + remind
        result = {
            "decision": "block",
            "reason": (
                "[EF Memory] Active working session detected. Before stopping, consider: "
                "(1) /memory-save if you discovered lessons or made important decisions, "
                "(2) check .memory/working/findings.md for unharvested insights. "
                "Say 'done' to stop without saving."
            ),
        }
        print(json.dumps(result))

    # Auto-compact if waste ratio exceeds threshold
    try:
        sys.path.insert(0, str(_MEMORY_DIR))
        from lib.compaction import get_compaction_stats, compact

        compact_config = config.get("compaction", {})
        threshold = compact_config.get("auto_suggest_threshold", 2.0)
        archive_rel = compact_config.get("archive_dir", ".memory/archive")
        archive_dir = _PROJECT_ROOT / archive_rel
        events_path = _MEMORY_DIR / "events.jsonl"

        stats = get_compaction_stats(events_path, threshold=threshold)
        if stats.suggest_compact:
            report = compact(events_path, archive_dir, config)
            if report.lines_archived > 0:
                # Non-blocking: just report in additionalContext
                compact_msg = (
                    f"[EF Memory] Auto-compacted events.jsonl: "
                    f"{report.lines_before} → {report.lines_after} lines, "
                    f"{report.lines_archived} archived to {report.quarters_touched}"
                )
                print(json.dumps({"additionalContext": compact_msg}))
    except Exception:
        pass  # Never block stopping on compact failure

    sys.exit(0)


if __name__ == "__main__":
    main()
