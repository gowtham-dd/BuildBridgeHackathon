"""
AI Analysis Pipeline
Uses Groq (LLaMA-3-8B-Instant) via LangChain.
Monte Carlo sampling: runs N inference passes with temperature variation,
then aggregates results for higher reliability/accuracy.
"""

import asyncio
import json
import logging
import os
import re
from collections import Counter
from typing import Any

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from models.response import AnalyzeResponse
from models.entities import EntitiesModel
from prompts.analysis_prompt import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)

# ── Monte Carlo Config ─────────────────────────────────────────────────────────
MC_RUNS = int(os.getenv("MC_RUNS", "3"))
MC_TEMPERATURES = [0.0, 0.2, 0.4]
MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "6000"))


def _get_llm(temperature: float = 0.1) -> ChatGroq:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable not set")
    return ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=temperature,
        api_key=api_key,
        max_tokens=500,
    )


def _truncate(text: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n\n[... MIDDLE TRUNCATED FOR CONTEXT WINDOW ...]\n\n" + text[-half:]


def _parse_llm_json(raw: str) -> dict | None:
    """Robustly extract JSON from LLM response (handles markdown fences)."""
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning(f"Could not parse LLM JSON: {raw[:300]}")
    return None


# ── UPDATED FUNCTION ───────────────────────────────────────────────────────────
async def _single_run(text: str, temperature: float) -> dict | None:
    """Single inference pass with retry for rate limits."""
    for attempt in range(3):
        try:
            llm = _get_llm(temperature)
            system = build_system_prompt()
            user = build_user_prompt(text)

            messages = [
                SystemMessage(content=system),
                HumanMessage(content=user)
            ]

            # 🔥 FIX: removed asyncio.to_thread
            response = llm.invoke(messages)

            return _parse_llm_json(response.content)

        except Exception as e:
            if "429" in str(e):
                wait = 5 * (attempt + 1)
                logger.warning(f"Rate limited. Retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                logger.error(f"LLM run failed at temp={temperature}: {e}")
                return None

    return None


# ── Aggregation ────────────────────────────────────────────────────────────────

def _majority_vote_sentiment(sentiments: list[str]) -> str:
    valid = [s.lower() for s in sentiments if s.lower() in ("positive", "neutral", "negative")]
    if not valid:
        return "neutral"
    return Counter(valid).most_common(1)[0][0]


def _best_summary(summaries: list[str]) -> str:
    valid = [s.strip() for s in summaries if s and len(s.strip()) > 20]
    if not valid:
        return "Summary not available."
    return max(valid, key=len)


def _merge_entities(all_entities: list[dict]) -> EntitiesModel:
    fields = ["names", "dates", "organizations", "amounts", "locations"]
    counts: dict[str, Counter] = {f: Counter() for f in fields}
    casing: dict[str, dict[str, Counter]] = {f: {} for f in fields}

    for ent_dict in all_entities:
        if not isinstance(ent_dict, dict):
            continue
        for field in fields:
            items = ent_dict.get(field, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str) and item.strip():
                        key = item.strip().lower()
                        counts[field][key] += 1
                        casing[field].setdefault(key, Counter())[item.strip()] += 1

    threshold = max(1, len(all_entities) // 2)
    result: dict[str, list[str]] = {}

    for field in fields:
        consensus = []
        for key, count in counts[field].items():
            if count >= threshold:
                best_casing = casing[field][key].most_common(1)[0][0]
                consensus.append(best_casing)
        result[field] = sorted(set(consensus))[:20]

    return EntitiesModel(**result)


# ── UPDATED MAIN PIPELINE ──────────────────────────────────────────────────────

async def run_analysis(raw_text: str, file_name: str) -> AnalyzeResponse:
    truncated = _truncate(raw_text)
    temperatures = MC_TEMPERATURES[:MC_RUNS]

    logger.info(f"Starting Monte Carlo analysis | runs={MC_RUNS} | text_len={len(truncated)}")

    # 🔥 FIX: Sequential execution with delay
    raw_results = []
    for t in temperatures:
        res = await _single_run(truncated, t)
        raw_results.append(res)
        await asyncio.sleep(2)  # prevent rate limit

    results = [r for r in raw_results if r is not None]
    logger.info(f"MC completed | successful_runs={len(results)}/{MC_RUNS}")

    if not results:
        raise RuntimeError("All LLM inference passes failed. Check GROQ_API_KEY and model availability.")

    summaries = [r.get("summary", "") for r in results]
    sentiments = [r.get("sentiment", "neutral") for r in results]
    entities_raw = [r.get("entities", {}) for r in results]

    final_summary = _best_summary(summaries)
    final_sentiment = _majority_vote_sentiment(sentiments)
    final_entities = _merge_entities(entities_raw)

    logger.info(f"Analysis complete | sentiment={final_sentiment} | summary_len={len(final_summary)}")

    return AnalyzeResponse(
        status="success",
        fileName=file_name,
        summary=final_summary,
        entities=final_entities,
        sentiment=final_sentiment,
    )