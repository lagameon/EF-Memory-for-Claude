"""
EF Memory V2 — LLM Prompt Templates (M6)

Centralized prompt templates for the reasoning engine.
Each function returns a (system_prompt, user_prompt) tuple
ready for LLMProvider.complete().

All prompts instruct the LLM to return structured JSON.
Each function accepts max_input_chars to enforce token budget.

No external dependencies — pure Python stdlib.
"""

import json
from typing import Tuple


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_MAX_INPUT_CHARS = 12000


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, appending ellipsis if truncated."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


def _entries_to_compact_text(entries: list, max_chars: int) -> str:
    """
    Serialize a list of entry dicts to compact text for LLM prompts.

    Each entry is formatted as a brief summary. Entries are added
    until max_chars is reached.
    """
    parts = []
    current_len = 0
    for entry in entries:
        eid = entry.get("id", "?")
        etype = entry.get("type", "?")
        classification = entry.get("classification", "?")
        severity = entry.get("severity", "?")
        title = entry.get("title", "?")
        rule = entry.get("rule", "")
        tags = entry.get("tags", [])
        sources = entry.get("source", [])

        line = (
            f"[{eid}] ({etype}/{classification}/{severity}) "
            f"{title}"
        )
        if rule:
            line += f"\n  Rule: {rule}"
        if tags:
            line += f"\n  Tags: {', '.join(tags)}"
        if sources:
            line += f"\n  Sources: {', '.join(sources[:3])}"
        line += "\n"

        if current_len + len(line) > max_chars:
            parts.append("... (entries truncated due to token budget)\n")
            break
        parts.append(line)
        current_len += len(line)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

def correlation_prompt(
    entries_text: str,
    heuristic_groups_text: str,
    max_input_chars: int = _DEFAULT_MAX_INPUT_CHARS,
) -> Tuple[str, str]:
    """
    Build prompts for cross-memory correlation analysis.

    Returns:
        (system_prompt, user_prompt)
    """
    system = (
        "You are an expert analyst for a project memory system. "
        "Your task is to analyze memory entries and identify meaningful "
        "relationships beyond simple tag overlap. "
        "Look for: causal chains, shared root causes, complementary rules, "
        "and temporal patterns.\n\n"
        "Return ONLY valid JSON with this structure:\n"
        '{"groups": [\n'
        '  {"entry_ids": ["id1", "id2"], '
        '"relationship": "description", '
        '"strength": 0.8}\n'
        "]}"
    )

    user = _truncate(
        f"Memory entries:\n{entries_text}\n\n"
        f"Heuristic groups already found:\n{heuristic_groups_text}\n\n"
        "Find additional meaningful correlations between entries. "
        "Focus on relationships the heuristic analysis may have missed. "
        "Return JSON only.",
        max_input_chars,
    )
    return system, user


def contradiction_prompt(
    candidate_pairs_text: str,
    max_input_chars: int = _DEFAULT_MAX_INPUT_CHARS,
) -> Tuple[str, str]:
    """
    Build prompts for contradiction detection.

    Returns:
        (system_prompt, user_prompt)
    """
    system = (
        "You are an expert analyst for a project memory system. "
        "Your task is to determine if candidate entry pairs actually "
        "contradict each other. A contradiction means two rules or "
        "lessons give conflicting guidance for the same situation.\n\n"
        "Return ONLY valid JSON with this structure:\n"
        '{"contradictions": [\n'
        '  {"entry_id_a": "id1", "entry_id_b": "id2", '
        '"type": "rule_conflict", '
        '"explanation": "why they conflict", '
        '"confidence": 0.9}\n'
        "]}"
    )

    user = _truncate(
        f"Candidate contradiction pairs:\n{candidate_pairs_text}\n\n"
        "For each pair, determine if there is a genuine contradiction. "
        "Consider context — two rules may seem contradictory but apply "
        "to different situations. Return JSON only.",
        max_input_chars,
    )
    return system, user


def synthesis_prompt(
    cluster_text: str,
    max_input_chars: int = _DEFAULT_MAX_INPUT_CHARS,
) -> Tuple[str, str]:
    """
    Build prompts for knowledge synthesis (multiple entries → principle).

    Returns:
        (system_prompt, user_prompt)
    """
    system = (
        "You are an expert analyst for a project memory system. "
        "Your task is to synthesize a group of related memory entries "
        "into a single consolidated principle or guideline.\n\n"
        "Return ONLY valid JSON with this structure:\n"
        '{"syntheses": [\n'
        '  {"source_entry_ids": ["id1", "id2", "id3"], '
        '"proposed_title": "short title", '
        '"proposed_principle": "the consolidated rule/principle", '
        '"rationale": "why these entries form a coherent principle"}\n'
        "]}"
    )

    user = _truncate(
        f"Related entry clusters:\n{cluster_text}\n\n"
        "For each cluster, propose a consolidated principle that "
        "captures the essential knowledge from all entries. "
        "The principle should be actionable and concise. "
        "Return JSON only.",
        max_input_chars,
    )
    return system, user


def risk_prompt(
    query: str,
    results_text: str,
    context_text: str,
    max_input_chars: int = _DEFAULT_MAX_INPUT_CHARS,
) -> Tuple[str, str]:
    """
    Build prompts for context-aware risk assessment.

    Returns:
        (system_prompt, user_prompt)
    """
    system = (
        "You are an expert analyst for a project memory system. "
        "Your task is to assess risks based on the user's current "
        "context and retrieved memory entries.\n\n"
        "Return ONLY valid JSON with this structure:\n"
        '{"annotations": [\n'
        '  {"entry_id": "id1", '
        '"risk_level": "high", '
        '"annotation": "explanation of the risk", '
        '"related_entry_ids": ["id2"]}\n'
        "]}"
    )

    user = _truncate(
        f"User query: {query}\n\n"
        f"Context: {context_text}\n\n"
        f"Retrieved entries:\n{results_text}\n\n"
        "Assess the risk level for each entry in the user's context. "
        "Consider entry confidence, source validity, and relevance. "
        "Return JSON only.",
        max_input_chars,
    )
    return system, user


def single_entry_prompt(
    entry_text: str,
    related_entries_text: str,
    max_input_chars: int = _DEFAULT_MAX_INPUT_CHARS,
) -> Tuple[str, str]:
    """
    Build prompts for single-entry deep analysis.

    Returns:
        (system_prompt, user_prompt)
    """
    system = (
        "You are an expert analyst for a project memory system. "
        "Your task is to provide deep analysis of a single memory entry "
        "in context of related entries.\n\n"
        "Return ONLY valid JSON with this structure:\n"
        '{"analysis": {\n'
        '  "correlations": [{"entry_id": "id", "relationship": "desc"}],\n'
        '  "contradictions": [{"entry_id": "id", "explanation": "desc"}],\n'
        '  "risk_level": "low",\n'
        '  "suggestions": ["suggestion1"]\n'
        "}}"
    )

    user = _truncate(
        f"Entry to analyze:\n{entry_text}\n\n"
        f"Related entries:\n{related_entries_text}\n\n"
        "Provide a comprehensive analysis of this entry. "
        "Return JSON only.",
        max_input_chars,
    )
    return system, user
