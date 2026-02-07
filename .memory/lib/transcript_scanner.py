"""
EF Memory V3 — Transcript Scanner

Reads Claude Code conversation transcripts (JSONL) and scans for
memory-worthy patterns. Creates draft entries in .memory/drafts/
for human review.

This module bridges the gap between normal conversations (no working
memory session) and the draft queue system (auto_capture.py).

Integration:
  - Stop hook calls scan_conversation_for_drafts() when no session exists
  - Reuses _extract_candidates() from working_memory.py (6 harvest patterns)
  - Reuses _convert_candidate_to_entry() for schema-compliant entries
  - Writes to .memory/drafts/ via create_draft() (never events.jsonl)

No external dependencies — pure Python stdlib + internal modules.
"""

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger("efm.transcript_scanner")

# Safety: skip transcripts larger than 10 MB to avoid blocking stop
_MAX_TRANSCRIPT_BYTES = 10 * 1024 * 1024


def read_transcript_messages(transcript_path: Path) -> List[str]:
    """Read a Claude Code transcript JSONL and extract assistant message texts.

    The JSONL format contains one JSON object per line. Each object has a
    "type" field. We look for assistant messages and extract text content
    blocks from message.content.

    Expected format:
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}]}}
        {"type": "human", "message": {"content": [{"type": "text", "text": "..."}]}}

    Returns:
        List of text strings from assistant turns only.
        Returns [] on any error (graceful degradation).
    """
    if not transcript_path.exists():
        return []

    try:
        file_size = transcript_path.stat().st_size
        if file_size > _MAX_TRANSCRIPT_BYTES:
            logger.info(
                f"Transcript too large ({file_size / 1024 / 1024:.1f} MB), "
                f"skipping scan"
            )
            return []
        if file_size == 0:
            return []
    except OSError:
        return []

    texts: List[str] = []
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if obj.get("type") != "assistant":
                    continue

                message = obj.get("message", {})
                content = message.get("content", [])
                if isinstance(content, str):
                    texts.append(content)
                    continue

                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            texts.append(text)
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"Cannot read transcript: {e}")
        return []

    return texts


def scan_conversation_for_drafts(
    transcript_path: Path,
    drafts_dir: Path,
    project_root: Path,
    config: dict,
) -> Dict:
    """Scan conversation transcript for memory-worthy patterns and create drafts.

    Steps:
        1. read_transcript_messages() → list of assistant texts
        2. Concatenate all text
        3. _extract_candidates() — reuse 6 harvest patterns from working_memory
        4. _convert_candidate_to_entry() — reuse converter from working_memory
        5. create_draft() — write to .memory/drafts/ (never events.jsonl)

    Args:
        transcript_path: Path to the conversation JSONL file
        drafts_dir: Path to .memory/drafts/
        project_root: Project root for source normalization
        config: EF Memory config dict

    Returns:
        {
            "candidates_found": int,
            "drafts_created": int,
            "draft_types": {"lesson": N, "constraint": N, ...},
            "errors": []
        }
    """
    result: Dict = {
        "candidates_found": 0,
        "drafts_created": 0,
        "draft_types": {},
        "errors": [],
    }

    # Step 1: Read transcript
    texts = read_transcript_messages(transcript_path)
    if not texts:
        return result

    # Step 2: Concatenate
    full_text = "\n\n".join(texts)

    # Step 3: Extract candidates (reuse working_memory patterns)
    try:
        from .working_memory import _extract_candidates, _convert_candidate_to_entry
    except ImportError as e:
        result["errors"].append(f"Cannot import working_memory: {e}")
        return result

    source_hint = f"conversation:{transcript_path.stem}"
    seen_titles: set = set()
    candidates = _extract_candidates(full_text, source_hint, seen_titles)
    result["candidates_found"] = len(candidates)

    if not candidates:
        return result

    # Step 4-5: Convert and create drafts
    try:
        from .auto_capture import create_draft
    except ImportError as e:
        result["errors"].append(f"Cannot import auto_capture: {e}")
        return result

    type_counts: Counter = Counter()
    for candidate in candidates:
        try:
            entry = _convert_candidate_to_entry(candidate, project_root)
            draft_info = create_draft(entry, drafts_dir)
            if draft_info.path.exists():
                result["drafts_created"] += 1
                type_counts[candidate.suggested_type] += 1
        except Exception as e:
            result["errors"].append(
                f"Draft failed for '{candidate.title[:50]}': {e}"
            )

    result["draft_types"] = dict(type_counts)
    return result
