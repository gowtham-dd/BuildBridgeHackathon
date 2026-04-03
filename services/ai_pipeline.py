"""
AI Analysis Pipeline
Uses Groq (LLaMA-3.3-70b-versatile) via LangChain.

Large doc strategy:
  - Splits text into chunks of ~4000 chars with overlap
  - Each chunk analyzed independently, results merged at end

Monte Carlo strategy:
  - 1 run per chunk for large docs (avoids rate limits)
  - MC runs=3 for small docs only
  - Sequential with backoff delay between calls
"""

import asyncio
import json
import logging
import os
import re
from collections import Counter

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from models.response import AnalyzeResponse
from models.entities import EntitiesModel
from prompts.analysis_prompt import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
MC_RUNS         = int(os.getenv("MC_RUNS", "3"))
MC_TEMPERATURES = [0.0, 0.2, 0.4]
CHUNK_SIZE      = int(os.getenv("CHUNK_SIZE", "4000"))
CHUNK_OVERLAP   = int(os.getenv("CHUNK_OVERLAP", "200"))
CALL_DELAY      = float(os.getenv("CALL_DELAY", "3.0"))


def _get_llm(temperature: float = 0.1) -> ChatGroq:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable not set")
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=temperature,
        api_key=api_key,
        max_tokens=1200,
    )


# ── Chunking ───────────────────────────────────────────────────────────────────

def _split_into_chunks(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if end < len(text):
            break_at = chunk.rfind("\n\n")
            if break_at == -1 or break_at < CHUNK_SIZE // 2:
                break_at = chunk.rfind(". ")
            if break_at != -1 and break_at > CHUNK_SIZE // 2:
                chunk = chunk[:break_at + 1]
        chunks.append(chunk.strip())
        start += len(chunk) - CHUNK_OVERLAP
    logger.info(f"Split document into {len(chunks)} chunks")
    return chunks


# ── JSON parsing ───────────────────────────────────────────────────────────────

def _parse_llm_json(raw: str) -> dict | None:
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


# ── Single LLM call with retry ─────────────────────────────────────────────────

async def _single_run(text: str, temperature: float) -> dict | None:
    for attempt in range(4):
        try:
            llm = _get_llm(temperature)
            messages = [
                SystemMessage(content=build_system_prompt()),
                HumanMessage(content=build_user_prompt(text)),
            ]
            response = llm.invoke(messages)
            return _parse_llm_json(response.content)
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                wait = 8 * (attempt + 1)
                logger.warning(f"Rate limited (attempt {attempt+1}). Waiting {wait}s...")
                await asyncio.sleep(wait)
            else:
                logger.error(f"LLM run failed at temp={temperature}: {e}")
                return None
    logger.error("All retry attempts exhausted.")
    return None


# ── Aggregation helpers ────────────────────────────────────────────────────────

def _majority_vote_sentiment(sentiments: list[str]) -> str:
    valid = [s.lower() for s in sentiments if s.lower() in ("positive", "neutral", "negative")]
    return Counter(valid).most_common(1)[0][0] if valid else "neutral"


def _majority_vote_str(values: list[str], fallback: str = "") -> str:
    valid = [v.strip() for v in values if v and v.strip()]
    return Counter(valid).most_common(1)[0][0] if valid else fallback


def _merge_summaries(summaries: list[str]) -> str:
    valid = [s.strip() for s in summaries if s and len(s.strip()) > 20]
    if not valid:
        return "Summary not available."
    if len(valid) == 1:
        return valid[0]
    combined = " ".join(valid)
    if len(combined) > 1200:
        combined = combined[:1200].rsplit(".", 1)[0] + "."
    return combined


def _merge_key_points(all_points: list[list]) -> list[str]:
    seen = set()
    result = []
    for points in all_points:
        if not isinstance(points, list):
            continue
        for p in points:
            if isinstance(p, str) and p.strip():
                key = p.strip().lower()
                if key not in seen:
                    seen.add(key)
                    result.append(p.strip())
    return result[:8]


def _merge_entities(all_entities: list[dict]) -> EntitiesModel:
    list_fields = ["names", "organizations", "locations", "dates",
                   "amounts", "emails", "phones", "urls", "keywords"]
    counts: dict[str, Counter] = {f: Counter() for f in list_fields}
    casing: dict[str, dict[str, Counter]] = {f: {} for f in list_fields}

    for ent_dict in all_entities:
        if not isinstance(ent_dict, dict):
            continue
        for field in list_fields:
            items = ent_dict.get(field, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str) and item.strip():
                        key = item.strip().lower()
                        counts[field][key] += 1
                        casing[field].setdefault(key, Counter())[item.strip()] += 1

    result: dict[str, list[str]] = {}
    for field in list_fields:
        result[field] = [
            casing[field][key].most_common(1)[0][0]
            for key in counts[field]
            if counts[field][key] >= 1
        ][:20]

    return EntitiesModel(**result)


# ── Main pipeline ──────────────────────────────────────────────────────────────

async def run_analysis(raw_text: str, file_name: str) -> AnalyzeResponse:
    chunks = _split_into_chunks(raw_text)
    is_large_doc = len(chunks) > 1

    all_summaries:  list[str]  = []
    all_sentiments: list[str]  = []
    all_entities:   list[dict] = []
    all_key_points: list[list] = []
    all_doc_types:  list[str]  = []
    all_languages:  list[str]  = []

    if is_large_doc:
        logger.info(f"Large doc mode | chunks={len(chunks)}")
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)}")
            result = await _single_run(chunk, temperature=0.1)
            if result:
                all_summaries.append(result.get("summary", ""))
                all_sentiments.append(result.get("sentiment", "neutral"))
                all_entities.append(result.get("entities", {}))
                all_key_points.append(result.get("key_points", []))
                all_doc_types.append(result.get("document_type", ""))
                all_languages.append(result.get("language", ""))
            if i < len(chunks) - 1:
                await asyncio.sleep(CALL_DELAY)
    else:
        logger.info(f"Small doc mode | MC runs={MC_RUNS}")
        for i, t in enumerate(MC_TEMPERATURES[:MC_RUNS]):
            result = await _single_run(chunks[0], temperature=t)
            if result:
                all_summaries.append(result.get("summary", ""))
                all_sentiments.append(result.get("sentiment", "neutral"))
                all_entities.append(result.get("entities", {}))
                all_key_points.append(result.get("key_points", []))
                all_doc_types.append(result.get("document_type", ""))
                all_languages.append(result.get("language", ""))
            if i < MC_RUNS - 1:
                await asyncio.sleep(CALL_DELAY)

    if not all_summaries:
        raise RuntimeError("All LLM inference passes failed. Check GROQ_API_KEY and model availability.")

    return AnalyzeResponse(
        status="success",
        fileName=file_name,
        document_type=_majority_vote_str(all_doc_types, "Other"),
        summary=_merge_summaries(all_summaries),
        key_points=_merge_key_points(all_key_points),
        entities=_merge_entities(all_entities),
        sentiment=_majority_vote_sentiment(all_sentiments),
        language=_majority_vote_str(all_languages, "English"),
    )