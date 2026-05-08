"""Heuristic duplicate / copycat detection using text similarity.

Uses difflib.SequenceMatcher for zero-dependency pairwise similarity.
Flags pairs above a configurable threshold.
"""

from difflib import SequenceMatcher
from typing import List, Dict
import re

SIMILARITY_THRESHOLD = 0.55  # Flag pairs above this


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip punctuation, collapse whitespace."""
    text = str(text).lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def detect_duplicates(results: List[Dict]) -> List[Dict]:
    """Find potential duplicate/copycat applications.

    Compares the 'duplicate_hint' field (what the startup is building)
    across all pairs. Returns list of flagged pairs with similarity score.
    """
    hints = []
    for r in results:
        raw_hint = r.get("duplicate_hint", "")
        if not raw_hint:
            raw_hint = r.get("raw_data", {}).get("what_building", "")
        hints.append({
            "id": r["application_id"],
            "name": r.get("startup_name", ""),
            "text": _normalize(raw_hint),
        })

    pairs = []
    n = len(hints)
    for i in range(n):
        if not hints[i]["text"]:
            continue
        for j in range(i + 1, n):
            if not hints[j]["text"]:
                continue
            sim = SequenceMatcher(None, hints[i]["text"], hints[j]["text"]).ratio()
            if sim >= SIMILARITY_THRESHOLD:
                pairs.append({
                    "app_a_id": hints[i]["id"],
                    "app_a_name": hints[i]["name"],
                    "app_b_id": hints[j]["id"],
                    "app_b_name": hints[j]["name"],
                    "similarity": round(sim, 3),
                })

    # Sort by similarity descending
    pairs.sort(key=lambda x: x["similarity"], reverse=True)
    return pairs
