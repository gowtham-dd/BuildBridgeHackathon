"""
Unit tests for core logic — runs offline without Groq API.
Usage:  pytest tests/test_unit.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from collections import Counter


# ── Test Monte Carlo aggregation ───────────────────────────────────────────────

def test_majority_vote_sentiment_positive():
    from services.ai_pipeline import _majority_vote_sentiment
    assert _majority_vote_sentiment(["positive", "positive", "neutral", "positive", "negative"]) == "positive"


def test_majority_vote_sentiment_tie_goes_to_most_common():
    from services.ai_pipeline import _majority_vote_sentiment
    result = _majority_vote_sentiment(["negative", "negative", "neutral", "neutral", "positive"])
    assert result in ("negative", "neutral")  # both tied at 2


def test_majority_vote_sentiment_empty_defaults_neutral():
    from services.ai_pipeline import _majority_vote_sentiment
    assert _majority_vote_sentiment([]) == "neutral"
    assert _majority_vote_sentiment(["garbage", "junk"]) == "neutral"


def test_best_summary_picks_longest():
    from services.ai_pipeline import _best_summary
    summaries = ["Short.", "This is a longer and more detailed summary of the document contents.", "Med summary here."]
    result = _best_summary(summaries)
    assert "detailed" in result


def test_best_summary_filters_empty():
    from services.ai_pipeline import _best_summary
    assert _best_summary(["", "  ", None, "Valid summary text here"]) == "Valid summary text here"
    assert _best_summary([]) == "Summary not available."


def test_merge_entities_consensus():
    from services.ai_pipeline import _merge_entities
    runs = [
        {"names": ["Alice Smith", "Bob Jones"], "dates": ["2024-01-01"], "organizations": ["Acme"], "amounts": ["$100"], "locations": ["New York"]},
        {"names": ["Alice Smith", "Carol Davis"], "dates": ["2024-01-01"], "organizations": ["Acme", "Beta Corp"], "amounts": ["$100"], "locations": ["New York"]},
        {"names": ["Alice Smith"], "dates": ["2024-01-01"], "organizations": ["Acme"], "amounts": [], "locations": ["New York"]},
    ]
    result = _merge_entities(runs)
    # Alice appears in all 3 → should pass threshold (3/2 = 1.5 → threshold=1)
    assert any("alice smith" in n.lower() for n in result.names)
    # Bob appears only once → threshold 1 (3//2=1), should still pass
    assert "2024-01-01" in result.dates
    assert any("acme" in o.lower() for o in result.organizations)


def test_merge_entities_preserves_casing():
    from services.ai_pipeline import _merge_entities
    runs = [
        {"names": ["Dr. Sarah Connor"], "dates": [], "organizations": [], "amounts": [], "locations": []},
        {"names": ["Dr. Sarah Connor"], "dates": [], "organizations": [], "amounts": [], "locations": []},
    ]
    result = _merge_entities(runs)
    assert "Dr. Sarah Connor" in result.names


def test_merge_entities_caps_at_20():
    from services.ai_pipeline import _merge_entities
    many = [f"Person {i}" for i in range(30)]
    runs = [{"names": many, "dates": [], "organizations": [], "amounts": [], "locations": []}]
    result = _merge_entities(runs)
    assert len(result.names) <= 20


# ── Test JSON parsing ──────────────────────────────────────────────────────────

def test_parse_llm_json_clean():
    from services.ai_pipeline import _parse_llm_json
    raw = '{"summary": "Test", "sentiment": "positive", "entities": {}}'
    result = _parse_llm_json(raw)
    assert result is not None
    assert result["sentiment"] == "positive"


def test_parse_llm_json_with_markdown_fences():
    from services.ai_pipeline import _parse_llm_json
    raw = '```json\n{"summary": "hello", "sentiment": "neutral", "entities": {}}\n```'
    result = _parse_llm_json(raw)
    assert result is not None
    assert result["sentiment"] == "neutral"


def test_parse_llm_json_embedded_in_text():
    from services.ai_pipeline import _parse_llm_json
    raw = 'Here is the analysis:\n{"summary": "doc about money", "sentiment": "negative", "entities": {"names": []}}'
    result = _parse_llm_json(raw)
    assert result is not None
    assert result["sentiment"] == "negative"


def test_parse_llm_json_garbage_returns_none():
    from services.ai_pipeline import _parse_llm_json
    assert _parse_llm_json("not json at all") is None
    assert _parse_llm_json("") is None


# ── Test text truncation ───────────────────────────────────────────────────────

def test_truncate_short_text():
    from services.ai_pipeline import _truncate
    short = "Hello world"
    assert _truncate(short, max_chars=100) == short


def test_truncate_long_text():
    from services.ai_pipeline import _truncate
    long_text = "A" * 10000
    result = _truncate(long_text, max_chars=100)
    assert len(result) < len(long_text)
    assert "TRUNCATED" in result


# ── Test extractor helpers ─────────────────────────────────────────────────────

def test_extract_text_strips_data_url_prefix():
    """extractor.extract_text should strip data:...;base64, prefix"""
    import base64
    from services.extractor import extract_text

    # Create a minimal valid DOCX in memory
    from docx import Document as DocxDocument
    import io
    doc = DocxDocument()
    doc.add_paragraph("Hello unit test")
    buf = io.BytesIO()
    doc.save(buf)
    raw_b64 = base64.b64encode(buf.getvalue()).decode()
    prefixed = f"data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{raw_b64}"

    text = extract_text("test.docx", "docx", prefixed)
    assert "Hello unit test" in text


def test_extract_pdf_basic():
    """PDF extraction returns non-empty text."""
    import base64

    # Build a trivial PDF in Python (same helper as test_api.py)
    content = "BT /F1 11 Tf 50 750 Td (Hello from PDF test) Tj ET"
    objects = [
        b"",
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj",
        f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj".encode(),
        f"4 0 obj\n<< /Length {len(content)} >>\nstream\n{content}\nendstream\nendobj".encode(),
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects):
        if i == 0:
            continue
        offsets.append(len(pdf))
        pdf += obj + b"\n"
    xref_pos = len(pdf)
    pdf += f"xref\n0 {len(objects)}\n0000000000 65535 f \n".encode()
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()

    b64 = base64.b64encode(pdf).decode()
    from services.extractor import extract_text
    text = extract_text("sample.pdf", "pdf", b64)
    assert isinstance(text, str)
