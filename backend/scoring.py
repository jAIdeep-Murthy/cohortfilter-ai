"""Async scoring pipeline. Creates jobs, streams progress, returns ranked results."""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List
from models import RubricConfig
from llm_adapter import score_with_llm, LLM_BASE_URL
from duplicate_detector import detect_duplicates


async def run_scoring_pipeline(
    applications: List[Dict],
    rubric: RubricConfig,
    progress_callback=None,
) -> tuple:
    """Score all applications against rubric. Returns (results, duplicates).

    Args:
        applications: List of dicts from CSV rows.
        rubric: The configured rubric.
        progress_callback: async fn(current, total) called after each app.

    Returns:
        (scored_results, duplicate_pairs)
    """
    rubric_dict = rubric.model_dump()
    results = []
    total = len(applications)

    for i, app in enumerate(applications):
        try:
            # Respect free tier rate limits (e.g. Groq 30 RPM)
            if i > 0 and ("openai" in str(LLM_BASE_URL) or "groq" in str(LLM_BASE_URL)):
                await asyncio.sleep(2.1)

            score_data = await score_with_llm(app, rubric_dict)

            # Merge score data with application metadata
            result = {
                "application_id": str(i + 1),
                "startup_name": app.get("startup_name", app.get("company_name", f"App-{i+1}")),
                "founder_name": app.get("founder_name", app.get("name", "Unknown")),
                "total_score": score_data.get("total_score", 0),
                "dimension_scores": score_data.get("dimension_scores", {}),
                "confidence": score_data.get("confidence", 0.0),
                "summary": score_data.get("summary", ""),
                "risk_flags": score_data.get("risk_flags", []),
                "duplicate_hint": score_data.get("duplicate_hint", ""),
                "website_status": score_data.get("website_status", "unknown"),
                "dealbreaker_hit": score_data.get("dealbreaker_hit", False),
                "dealbreaker_reason": score_data.get("dealbreaker_reason"),
                "rank": None,
                "raw_data": app,
            }
            results.append(result)

        except Exception as e:
            print(f"Scoring error for App {i+1}: {e}")
            # Don't let one bad row kill the whole pipeline
            results.append({
                "application_id": str(i + 1),
                "startup_name": app.get("startup_name", f"App-{i+1}"),
                "founder_name": app.get("founder_name", "Unknown"),
                "total_score": 0,
                "dimension_scores": {},
                "confidence": 0.0,
                "summary": f"Scoring error: {str(e)}",
                "risk_flags": ["SCORING_ERROR"],
                "duplicate_hint": "",
                "website_status": "unknown",
                "dealbreaker_hit": False,
                "dealbreaker_reason": None,
                "rank": None,
                "raw_data": app,
            })

        if progress_callback:
            await progress_callback(i + 1, total)

    # Sort by total_score descending (dealbreaker hits go to bottom)
    results.sort(key=lambda x: (not x["dealbreaker_hit"], x["total_score"]), reverse=True)

    # Assign ranks
    for i, r in enumerate(results):
        r["rank"] = i + 1

    # Detect duplicates using heuristic text similarity
    duplicates = detect_duplicates(results)

    # Annotate results with duplicate info
    dup_ids = set()
    for pair in duplicates:
        dup_ids.add(pair["app_a_id"])
        dup_ids.add(pair["app_b_id"])
    for r in results:
        if r["application_id"] in dup_ids:
            matching = [p for p in duplicates
                        if r["application_id"] in (p["app_a_id"], p["app_b_id"])]
            if matching and not r.get("duplicate_hint_flag"):
                other_id = matching[0]["app_b_id"] if matching[0]["app_a_id"] == r["application_id"] else matching[0]["app_a_id"]
                other = next((x for x in results if x["application_id"] == other_id), None)
                if other:
                    r["risk_flags"] = r.get("risk_flags", []) + [
                        f"Possible duplicate of {other['startup_name']} (similarity: {matching[0]['similarity']:.0%})"
                    ]
                    r["duplicate_hint_flag"] = True

    return results, duplicates
