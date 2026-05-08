"""LLM adapter — three modes: mock, openai, vllm.

Environment variables:
  LLM_MODE      "mock" | "openai" | "vllm"  (default: mock)
  LLM_BASE_URL  API base URL                 (for openai/vllm)
  LLM_MODEL     Model name                   (for openai/vllm)
  LLM_API_KEY   API key / token              (for openai/vllm)
"""

import asyncio
import json
import os
import random
import re
from typing import Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

MODE = os.getenv("LLM_MODE", "mock")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "meta-llama/Llama-3-70b-instruct")
LLM_API_KEY = os.getenv("LLM_API_KEY", "EMPTY")


# ── Scoring Prompt ──────────────────────────────────────────

def build_scoring_prompt(application: Dict, rubric_dict: Dict) -> str:
    dims = rubric_dict.get("dimensions", [])
    dim_lines = "\n".join(
        f"  - {d['name']} (weight {d['weight']:.0%}): {d.get('description', '')}"
        for d in dims
    )
    dim_keys = ", ".join(f'"{d["name"]}"' for d in dims)

    dbs = rubric_dict.get("dealbreakers", [])
    db_lines = "\n".join(f"  - {d['rule']}" for d in dbs) or "  (none)"

    app_lines = "\n".join(f"  {k}: {v}" for k, v in application.items() if v)

    return f"""You are an expert startup evaluator. Score this application. Return ONLY valid JSON, no other text.

PROGRAM: {rubric_dict.get('program_focus', 'General')}

DIMENSIONS (score each 0-1000):
{dim_lines}

DEALBREAKERS — CHECK CAREFULLY (set "dealbreaker": true if ANY apply):
{db_lines}
IMPORTANT: Check the team_size and mrr fields explicitly. If team_size is "1" or "solo", the "No solo founders" dealbreaker is triggered. If mrr is below the threshold, that dealbreaker is triggered. When a dealbreaker is triggered, set total_score to at most 150.

APPLICATION:
{app_lines}

Return EXACTLY this JSON (no markdown, no explanation):
{{
  "scores": {{ {dim_keys}: <int 0-1000> for each }},
  "total_score": <int 0-1000 weighted average, max 150 if dealbreaker hit>,
  "confidence": <float 0.0-1.0>,
  "shortlist": <bool true if score>=600 and no dealbreaker>,
  "dealbreaker": <bool — true if ANY dealbreaker rule is violated>,
  "dealbreaker_reason": <string explaining which rule was violated, or null>,
  "summary": "<2 sentence assessment>",
  "risk_flags": [<ONLY list significant concerns, max 2 items. Empty list if no major issues>],
  "website_status": "<live|dead|unknown>",
  "dimension_reasons": {{ {dim_keys}: "<1 sentence>" for each }}
}}"""


# ── Main Entry Point ────────────────────────────────────────

async def score_with_llm(application: Dict, rubric_dict: Dict) -> Dict:
    if MODE == "mock":
        return await _mock_score(application, rubric_dict)
    elif MODE in ("openai", "vllm"):
        return await _live_score(application, rubric_dict)
    else:
        raise ValueError(f"Unknown LLM_MODE: {MODE}")


# ── Live Scoring (OpenAI / vLLM) ────────────────────────────

async def _live_score(application: Dict, rubric_dict: Dict) -> Dict:
    import aiohttp

    prompt = build_scoring_prompt(application, rubric_dict)
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 800,
    }
    headers = {
        "Content-Type": "application/json",
    }
    if LLM_API_KEY and LLM_API_KEY != "EMPTY":
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    async with aiohttp.ClientSession() as session:
        max_retries = 3
        for attempt in range(max_retries):
            async with session.post(
                f"{LLM_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                if resp.status == 429:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt + random.uniform(1, 3))
                        continue
                    else:
                        raise RuntimeError(f"Rate limit exceeded after {max_retries} attempts.")
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"LLM API error {resp.status}: {text[:300]}")
                data = await resp.json()
                break

    raw_text = data["choices"][0]["message"]["content"]
    raw = _parse_json_response(raw_text)
    return _map_llm_output(raw, rubric_dict)

# ── LLM Document Rubric Extraction ──────────────────────────

async def extract_rubric_with_llm(document_text: str) -> Dict:
    """Extract a structured RubricConfig from a raw document using the live LLM."""
    if MODE == "mock":
        # Fallback to mock if API is mocked, though user requested live LLM
        pass # Handle mock case or assume this is only called when live
        
    import aiohttp
    
    # Trim document text if it's too long to prevent context overflow
    max_chars = 15000
    if len(document_text) > max_chars:
        document_text = document_text[:max_chars] + "... [TRUNCATED]"

    prompt = f"""You are an expert VC and accelerator program manager.
Read the following program documentation and extract the scoring rubric criteria into a strict JSON format.

DOCUMENT TEXT:
\"\"\"{document_text}\"\"\"

Extract the "program_focus", "dimensions", and "dealbreakers".
- "program_focus" is a short 1-sentence summary of the thesis.
- "dimensions" is a list of exactly 3 to 5 scoring categories (like Traction, Team, Market Fit). Ensure the weights sum to 1.0 (e.g., 0.4, 0.3, 0.3).
- "dealbreakers" is a list of strict exclusion rules (e.g., "No solo founders").

Return EXACTLY this JSON structure and absolutely nothing else:
{{
  "program_focus": "string",
  "dimensions": [
    {{
      "name": "string",
      "weight": float,
      "description": "string"
    }}
  ],
  "dealbreakers": [
    {{
      "rule": "string"
    }}
  ]
}}
"""
    
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 1000,
    }
    
    headers = {"Content-Type": "application/json"}
    if LLM_API_KEY and LLM_API_KEY != "EMPTY":
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"
        
    async with aiohttp.ClientSession() as session:
        max_retries = 3
        for attempt in range(max_retries):
            async with session.post(
                f"{LLM_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                if resp.status == 429:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt + random.uniform(1, 3))
                        continue
                    else:
                        raise RuntimeError(f"Rate limit exceeded after {max_retries} attempts.")
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"LLM API error {resp.status}: {text[:300]}")
                data = await resp.json()
                break

    raw_text = data["choices"][0]["message"]["content"]
    
    # Try to extract JSON from markdown if model wrapped it
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if match:
        raw_text = match.group(1)
        
    try:
        rubric_data = json.loads(raw_text)
        return rubric_data
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM rubric response as JSON: {raw_text[:200]}")


def _parse_json_response(text: str) -> Dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from markdown code block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try finding any JSON object
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}")


def _map_llm_output(raw: Dict, rubric_dict: Dict) -> Dict:
    """Map LLM JSON output to internal format used by scoring pipeline."""
    scores = raw.get("scores", {})
    reasons = raw.get("dimension_reasons", {})

    dimension_scores = {}
    for dim_name, score in scores.items():
        dimension_scores[dim_name] = {
            "score": max(0, min(1000, int(score))),
            "reason": reasons.get(dim_name, ""),
        }

    summary = raw.get("summary", "")
    return {
        "total_score": max(0, min(1000, int(raw.get("total_score", 0)))),
        "dimension_scores": dimension_scores,
        "confidence": round(float(raw.get("confidence", 0.5)), 2),
        "summary": summary,
        "risk_flags": raw.get("risk_flags", []),
        "duplicate_hint": summary[:200],
        "website_status": raw.get("website_status", "unknown"),
        "dealbreaker_hit": bool(raw.get("dealbreaker", False)),
        "dealbreaker_reason": raw.get("dealbreaker_reason"),
    }


# ── Mock Scoring ────────────────────────────────────────────

TRACTION_POS = ["revenue", "paying", "customers", "users", "mrr", "arr",
                "growing", "traction", "sales", "contracts", "pilot",
                "k mrr", "monthly", "recurring"]
TRACTION_NEG = ["pre-revenue", "no revenue", "idea stage", "no customers",
                "concept", "pre-launch", "no traction"]
TEAM_POS = ["co-founder", "cofounders", "team of", "engineers",
            "experience", "ex-google", "ex-meta", "phd", "serial",
            "technical", "full-time", "yoe", "years"]
TEAM_NEG = ["solo", "single founder", "part-time", "student project",
            "no technical"]
MARKET_POS = ["billion", "tam", "large market", "underserved",
              "growing market", "b2b", "enterprise", "tailwind"]
MARKET_NEG = ["saturated", "crowded", "small market", "niche hobby"]

SIGNAL_MAP = {
    "traction": (TRACTION_POS, TRACTION_NEG),
    "team": (TEAM_POS, TEAM_NEG),
    "market fit": (MARKET_POS, MARKET_NEG),
    "market": (MARKET_POS, MARKET_NEG),
    "mission": (MARKET_POS, MARKET_NEG),
    "mission alignment": (MARKET_POS, MARKET_NEG),
    "innovation": (TRACTION_POS, TRACTION_NEG),
    "product": (TRACTION_POS, TRACTION_NEG),
}


def _kw_score(text: str, pos: list, neg: list) -> int:
    t = text.lower()
    p = sum(1 for kw in pos if kw in t)
    n = sum(1 for kw in neg if kw in t)
    return max(50, min(950, 500 + p * 80 - n * 120 + random.randint(-60, 60)))


def _check_dealbreakers(app: Dict, dbs: list) -> tuple:
    app_text = " ".join(str(v) for v in app.values()).lower()
    for db in dbs:
        rule = db.get("rule", "").lower()
        if "solo" in rule or "single founder" in rule:
            ts = str(app.get("team_size", "")).strip()
            if ts in ("1", "solo", "1.0"):
                return True, "Solo founder (team_size = 1)"
        mrr_match = re.search(r'\$?([\d,]+)\s*k?\s*mrr', rule)
        if mrr_match:
            threshold = float(mrr_match.group(1).replace(",", ""))
            if "k" in rule:
                threshold *= 1000
            try:
                val = float(str(app.get("mrr", "0")).replace("$", "").replace(",", "").replace("k", "000").strip() or "0")
                if val < threshold:
                    return True, f"MRR ${val:.0f} below threshold ${threshold:.0f}"
            except ValueError:
                pass
    return False, None


async def _mock_score(application: Dict, rubric_dict: Dict) -> Dict:
    await asyncio.sleep(random.uniform(0.15, 0.4))

    app_text = " ".join(str(v) for v in application.values())
    dims = rubric_dict.get("dimensions", [])
    dbs = rubric_dict.get("dealbreakers", [])

    dimension_scores = {}
    weighted_total = 0.0

    for dim in dims:
        name = dim["name"]
        weight = dim["weight"]
        pos, neg = SIGNAL_MAP.get(name.lower(), (TRACTION_POS, TRACTION_NEG))
        score = _kw_score(app_text, pos, neg)
        sname = application.get("startup_name", "This startup")
        if score >= 750:
            reason = f"Strong {name.lower()} signals. {sname} shows clear execution evidence."
        elif score >= 500:
            reason = f"Moderate {name.lower()}. Some positive indicators but needs validation."
        elif score >= 300:
            reason = f"Weak {name.lower()} signals. Limited evidence in the application."
        else:
            reason = f"Very low {name.lower()}. Major concerns about viability."
        dimension_scores[name] = {"score": score, "reason": reason}
        weighted_total += score * weight

    total_score = int(weighted_total)
    db_hit, db_reason = _check_dealbreakers(application, dbs)
    if db_hit:
        total_score = min(total_score, 150)

    risk_flags = []
    if db_hit:
        risk_flags.append(f"DEALBREAKER: {db_reason}")
    try:
        mrr_val = float(str(application.get("mrr", "0")).replace("$", "").replace(",", "").replace("k", "000").strip() or "0")
        if mrr_val == 0:
            risk_flags.append("Pre-revenue")
    except ValueError:
        pass
    if str(application.get("team_size", "")).strip() in ("1", "solo"):
        risk_flags.append("Solo founder")

    what = application.get("what_building", application.get("description", ""))
    sname = application.get("startup_name", application.get("company_name", "Unknown"))

    if db_hit:
        summary = f"{sname} hit a dealbreaker and is not recommended. Review only if criteria change."
    elif total_score >= 700:
        top = max(dimension_scores.items(), key=lambda x: x[1]["score"])[0]
        summary = f"{sname} is a strong candidate with particular strength in {top}. Recommended for shortlist."
    elif total_score >= 450:
        summary = f"{sname} shows moderate potential but has gaps. Consider for extended review."
    else:
        summary = f"{sname} scores below threshold across most dimensions. Not recommended."

    return {
        "total_score": max(0, min(1000, total_score)),
        "dimension_scores": dimension_scores,
        "confidence": round(random.uniform(0.72, 0.95), 2),
        "summary": summary,
        "risk_flags": risk_flags,
        "duplicate_hint": str(what)[:200],
        "website_status": random.choice(["live", "live", "live", "unknown", "dead"]),
        "dealbreaker_hit": db_hit,
        "dealbreaker_reason": db_reason,
    }
