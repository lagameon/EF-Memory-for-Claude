#!/usr/bin/env python3
"""
EF Memory V2 — LLM Reasoning CLI

Cross-memory correlation, contradiction detection, knowledge synthesis,
and context-aware risk assessment.

Usage:
    python3 .memory/scripts/reasoning_cli.py                    # Full reasoning report
    python3 .memory/scripts/reasoning_cli.py --correlations      # Cross-memory correlations
    python3 .memory/scripts/reasoning_cli.py --contradictions    # Contradiction detection
    python3 .memory/scripts/reasoning_cli.py --syntheses         # Knowledge synthesis
    python3 .memory/scripts/reasoning_cli.py --risks "query"     # Context-aware risk assessment
    python3 .memory/scripts/reasoning_cli.py --no-llm            # Force heuristic-only mode
    python3 .memory/scripts/reasoning_cli.py --help              # Show help
"""

import json
import logging
import sys
from pathlib import Path

# Add .memory/ to import path
_SCRIPT_DIR = Path(__file__).resolve().parent
_MEMORY_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_MEMORY_DIR))

from lib.reasoning import (
    build_reasoning_report,
    find_correlations,
    detect_contradictions,
    suggest_syntheses,
    assess_risks,
)
from lib.auto_verify import _load_entries_latest_wins
from lib.llm_provider import create_llm_provider


def _parse_args(argv: list) -> dict:
    """Simple argument parser."""
    args = {
        "correlations": False,
        "contradictions": False,
        "syntheses": False,
        "risks": None,       # query string if --risks "query"
        "no_llm": False,
        "help": False,
    }
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--help", "-h"):
            args["help"] = True
        elif arg == "--correlations":
            args["correlations"] = True
        elif arg == "--contradictions":
            args["contradictions"] = True
        elif arg == "--syntheses":
            args["syntheses"] = True
        elif arg == "--risks":
            # Next argument is the query string
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                args["risks"] = argv[i + 1]
                i += 1
            else:
                args["risks"] = ""
        elif arg == "--no-llm":
            args["no_llm"] = True
        elif arg.startswith("--"):
            print(f"ERROR: Unknown option: {arg}")
            sys.exit(1)
        i += 1
    return args


def _get_llm_provider(config: dict, no_llm: bool):
    """Create LLM provider if available and not disabled."""
    if no_llm:
        return None
    reasoning_config = config.get("reasoning", {})
    if not reasoning_config.get("enabled", False):
        return None
    return create_llm_provider(reasoning_config)


# ---------------------------------------------------------------------------
# Printers
# ---------------------------------------------------------------------------

def _print_correlations(report):
    """Print correlation report."""
    print(f"Cross-Memory Correlations  [{report.mode}]")
    print(f"  Entries analyzed: {report.total_entries}")
    print(f"  Groups found:    {len(report.groups)}")

    for i, group in enumerate(report.groups, 1):
        strength_bar = "█" * max(1, int(group.strength * 5))
        print(f"\n  Group {i} [{strength_bar}] ({group.strength:.2f})")
        print(f"    Relationship: {group.relationship}")
        print(f"    Explanation:  {group.explanation}")
        print(f"    Entries:")
        for eid in group.entry_ids:
            print(f"      - {eid}")

    print(f"\n  Duration: {report.duration_ms:.0f}ms")


def _print_contradictions(report):
    """Print contradiction report."""
    print(f"Contradiction Detection  [{report.mode}]")
    print(f"  Entries analyzed: {report.total_entries}")
    print(f"  Pairs found:     {len(report.pairs)}")

    for i, pair in enumerate(report.pairs, 1):
        conf_marker = {True: "!!", False: "?"}.get(pair.confidence > 0.7, "~")
        print(f"\n  {i}. [{conf_marker}] {pair.type} (confidence: {pair.confidence:.2f})")
        print(f"     Entry A: {pair.entry_id_a}")
        print(f"     Entry B: {pair.entry_id_b}")
        print(f"     Explanation: {pair.explanation}")

    print(f"\n  Duration: {report.duration_ms:.0f}ms")


def _print_syntheses(report):
    """Print synthesis suggestions."""
    print(f"Knowledge Synthesis  [{report.mode}]")
    print(f"  Entries analyzed: {report.total_entries}")
    print(f"  Suggestions:     {len(report.suggestions)}")

    for i, sugg in enumerate(report.suggestions, 1):
        print(f"\n  {i}. {sugg.proposed_title or '(no title — needs LLM)'}")
        if sugg.proposed_principle:
            print(f"     Principle: {sugg.proposed_principle}")
        print(f"     Rationale: {sugg.rationale}")
        print(f"     Source entries ({len(sugg.source_entry_ids)}):")
        for eid in sugg.source_entry_ids:
            print(f"       - {eid}")

    print(f"\n  Duration: {report.duration_ms:.0f}ms")


def _print_risks(report):
    """Print risk assessment."""
    print(f"Risk Assessment  [{report.mode}]")
    print(f"  Query: {report.query}")
    print(f"  Annotations: {len(report.annotations)}")

    level_icons = {
        "high": "🔴",
        "medium": "🟡",
        "low": "🟢",
        "info": "ℹ️ ",
    }

    for ann in report.annotations:
        icon = level_icons.get(ann.risk_level, "?")
        print(f"\n  {icon} [{ann.risk_level.upper()}] {ann.entry_id}")
        print(f"     {ann.annotation}")
        if ann.related_entry_ids:
            print(f"     Related: {', '.join(ann.related_entry_ids)}")

    print(f"\n  Duration: {report.duration_ms:.0f}ms")


def _print_reasoning_report(report):
    """Print full reasoning report."""
    print(f"EF Memory Reasoning Report  [{report.mode}]")
    print(f"  Total entries: {report.total_entries}")
    if report.llm_calls > 0:
        print(f"  LLM calls:    {report.llm_calls}")
        print(f"  LLM tokens:   {report.llm_tokens_used}")

    if report.correlation_report:
        cr = report.correlation_report
        print(f"\n  Correlations: {len(cr.groups)} group(s) [{cr.mode}]")
        for group in cr.groups:
            print(f"    - {group.relationship}: {group.entry_ids} ({group.strength:.2f})")

    if report.contradiction_report:
        cdr = report.contradiction_report
        print(f"\n  Contradictions: {len(cdr.pairs)} pair(s) [{cdr.mode}]")
        for pair in cdr.pairs:
            print(f"    - [{pair.type}] {pair.entry_id_a} vs {pair.entry_id_b}"
                  f" ({pair.confidence:.2f})")
            print(f"      {pair.explanation}")

    if report.synthesis_report:
        sr = report.synthesis_report
        print(f"\n  Synthesis: {len(sr.suggestions)} suggestion(s) [{sr.mode}]")
        for sugg in sr.suggestions:
            title = sugg.proposed_title or "(needs LLM)"
            print(f"    - {title}: {sugg.source_entry_ids}")

    print(f"\n  Duration: {report.duration_ms:.0f}ms")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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
        config = json.loads(config_path.read_text())

    # Check for events
    if not events_path.exists() or events_path.stat().st_size <= 1:
        print("No entries in events.jsonl. Nothing to analyze.")
        sys.exit(0)

    # LLM provider
    llm_provider = _get_llm_provider(config, args["no_llm"])
    mode_label = "heuristic" if llm_provider is None else "LLM-enriched"

    # Load entries for sub-commands
    entries = _load_entries_latest_wins(events_path)
    active = {eid: e for eid, e in entries.items() if not e.get("deprecated", False)}

    if llm_provider is None and not args["no_llm"]:
        reasoning_cfg = config.get("reasoning", {})
        if not reasoning_cfg.get("enabled", False):
            print("Note: LLM reasoning disabled (reasoning.enabled=false in config)."
                  " Running in heuristic-only mode.\n")
        else:
            print("Note: LLM provider not available. Running in heuristic-only mode.\n")

    # --- Mode: --correlations ---
    if args["correlations"]:
        report = find_correlations(active, config, llm_provider=llm_provider)
        _print_correlations(report)
        sys.exit(0)

    # --- Mode: --contradictions ---
    if args["contradictions"]:
        report = detect_contradictions(active, config, llm_provider=llm_provider)
        _print_contradictions(report)
        sys.exit(0)

    # --- Mode: --syntheses ---
    if args["syntheses"]:
        report = suggest_syntheses(active, config, llm_provider=llm_provider)
        _print_syntheses(report)
        sys.exit(0)

    # --- Mode: --risks "query" ---
    if args["risks"] is not None:
        from dataclasses import dataclass

        @dataclass
        class _SimpleResult:
            entry_id: str

        query = args["risks"] or "general"
        results = [_SimpleResult(entry_id=eid) for eid in active]
        report = assess_risks(query, results, active, config, llm_provider=llm_provider)
        _print_risks(report)
        sys.exit(0)

    # --- Default: full report ---
    report = build_reasoning_report(
        events_path, config, project_root,
        llm_provider=llm_provider,
    )
    _print_reasoning_report(report)


if __name__ == "__main__":
    main()
