# DocuSense — AI Document Analyzer API

> **Hackathon Track 2** · FastAPI · Groq LLaMA-3.3-70B · Monte Carlo consensus · Google Vision API · Tesseract fallback · python-docx

---

## 🚀 Live Demo
- **API:** `https://buildbridgehackathon.onrender.com/api/document-analyze`
- **Web UI:** `https://buildbridgehackathon.onrender.com/`
- **Swagger Docs:** `https://buildbridgehackathon.onrender.com/docs`

---
## 🤖 AI Tools Used

* **Groq LLaMA-3.3-70B (`llama-3.3-70b-versatile`)**
* **Google Cloud Vision API**
* **Tesseract OCR**
* **LangChain**

---


## 📐 Architecture & Approach

```
Request (File Upload — PDF / DOCX / Image)
        │
        ▼
┌──────────────────────┐
│   Auth Middleware    │  x-api-key header validation
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│                    Extraction Layer                          │
│                                                              │
│  PDF   → Google Vision API (pages rendered as PNG → OCR)    │
│           └─ Fallback: PyMuPDF text extraction               │
│  DOCX  → python-docx  (.doc auto-converted via LibreOffice)  │
│  Image → Google Vision API (document_text_detection)        │
│           └─ Fallback: Tesseract OCR                         │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│               Monte Carlo AI Pipeline                        │
│                                                              │
│  Small docs  → 3 Groq LLaMA-3.3-70B passes                  │
│                Temperature ladder: [0.0, 0.2, 0.4]          │
│  Large docs  → 1 pass per chunk (4000 chars, 200 overlap)    │
│                                                              │
│  Aggregation:                                                │
│    summary      → longest / most detailed across runs       │
│    key_points   → union across chunks, deduplicated         │
│    sentiment    → majority vote                             │
│    entities     → union across all runs / chunks            │
│    document_type→ majority vote                             │
│    language     → majority vote                             │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
    Structured JSON response (10 entity types)
```

### Why Monte Carlo?
Single LLM calls are stochastic. Running multiple passes at varying temperatures:
- **Sentiment** — majority vote reduces single-pass hallucination
- **Entities** — union across runs ensures nothing is missed
- **Summary** — most detailed successful output is selected
- **Large docs** — chunked processing means no page is ever truncated or skipped

---

## 📦 Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI + Uvicorn |
| LLM | Groq · `llama-3.3-70b-versatile` |
| LLM Orchestration | LangChain + langchain-groq |
| PDF Extraction | Google Vision API (page-by-page PNG OCR) |
| PDF Fallback | PyMuPDF (fitz) |
| DOCX Extraction | python-docx |
| .doc Conversion | LibreOffice headless |
| Image OCR | Google Vision API (primary) · Tesseract (fallback) |
| Deployment | Render (Docker runtime) |
| Validation | Pydantic v2 |

---

## 📁 Project Structure

```
doc-analyzer/
├── main.py                    # FastAPI app entry point
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Container build (Tesseract + LibreOffice + Python 3.11)
├── render.yaml                # Render deployment config (Docker runtime)
├── README.md
│
├── routers/
│   └── analyze.py             # POST /api/document-analyze + auth + file upload
│
├── models/
│   ├── request.py             # (legacy — endpoint now uses UploadFile directly)
│   ├── response.py            # AnalyzeResponse schema
│   └── entities.py            # EntitiesModel — 10 entity categories
│
├── services/
│   ├── extractor.py           # PDF / DOCX / Image extraction (Google Vision)
│   └── ai_pipeline.py         # Monte Carlo LLM orchestration + chunking + aggregation
│
├── prompts/
│   └── analysis_prompt.py     # System + user prompt builders
│
└── static/
    └── index.html             # Web UI (Chart.js — doughnut + bar charts + entity grid)
```

---

## 🔌 API Reference

### `POST /api/document-analyze`

Accepts a file directly as **multipart/form-data** — no base64 encoding needed.

**Headers**

| Key | Value |
|---|---|
| `x-api-key` | `mysecretkey123` |

**Body**

| Key | Type | Value |
|---|---|---|
| `file` | File | your document (pdf / docx / doc / png / jpg / jpeg / webp / tiff / bmp / gif) |

**Response**
```json
{
  "status": "success",
  "fileName": "invoice.pdf",
  "document_type": "Invoice",
  "language": "English",
  "summary": "This document is an invoice from Acme Corp...",
  "key_points": [
    "Total invoice amount is $12,500 due by 15 February 2024",
    "Services rendered include software development and consulting",
    "Payment terms specify a 15-day settlement window"
  ],
  "entities": {
    "names": ["John Smith", "Priya Rajan"],
    "organizations": ["Acme Corp", "Tech Solutions Ltd"],
    "locations": ["New York, NY", "San Francisco"],
    "dates": ["2024-01-15", "Q1 2024"],
    "amounts": ["$12,500.00"],
    "emails": ["john@acmecorp.com"],
    "phones": ["+1-800-555-0199"],
    "urls": ["www.acmecorp.com"],
    "keywords": ["invoice", "software development", "consulting", "payment terms"]
  },
  "sentiment": "neutral"
}
```

**Error responses**

| Code | Meaning |
|---|---|
| 401 | Invalid or missing x-api-key |
| 400 | Unsupported file type or empty file |
| 413 | File too large (max 20 MB) |
| 422 | No text could be extracted from the document |
| 500 | Internal server error |

---

## 🧪 Testing the API with Postman

### Step 1 — Create a new request
- Method: **POST**
- URL: `https://buildbridgehackathon.onrender.com/api/document-analyze`

### Step 2 — Add the API key header
Go to the **Headers** tab and add:

| Key | Value |
|---|---|
| `x-api-key` | `mysecretkey123` |

### Step 3 — Attach your file
Go to **Body** tab → select **form-data**

Add a row:

| Key | Type | Value |
|---|---|---|
| `file` | **File** ← change the dropdown from Text to File | click Select Files → pick your document |

> ⚠️ The Type column defaults to `Text` — you **must** switch it to **File** or the upload won't work.

### Step 4 — Hit Send

You will get back a full JSON response with summary, key points, 10 entity categories, sentiment, document type, and detected language.

---

## 🌐 Testing via Swagger UI

Visit [`https://buildbridgehackathon.onrender.com/docs`](https://buildbridgehackathon.onrender.com/docs) in your browser.

1. Click `POST /api/document-analyze` → **Try it out**
2. Enter `mysecretkey123` in the `x-api-key` field
3. Click **Choose File** and select your document
4. Click **Execute**

---

## 🏷 Extracted Entities — All 10 Categories

| Entity | What it extracts |
|---|---|
| `names` | Full person names (e.g. "Dr. John Smith") |
| `organizations` | Companies, universities, institutions, brands |
| `locations` | Cities, states, countries, addresses |
| `dates` | All date and time references |
| `amounts` | Monetary values with currency symbols |
| `emails` | Email addresses |
| `phones` | Phone, mobile, fax numbers |
| `urls` | Websites, domains, social handles |
| `keywords` | Top 5–10 domain-specific terms or topics |

Plus `document_type` (Invoice / Resume / Contract / Report etc.) and `language` at the top level.

---

## 🖥 Web UI

Visit [`https://buildbridgehackathon.onrender.com`](https://buildbridgehackathon.onrender.com) for the visual interface.

- Drag & drop or browse to upload any supported file
- Enter `mysecretkey123` in the API Key field
- Visualizations include:
  - **Sentiment doughnut chart** — positive / neutral / negative weighting
  - **Entity distribution bar chart** — count across all 9 entity types
  - **Entity grid** — colour-coded tags for every extracted entity
  - **Key points** — numbered bullet findings from the document
  - **Raw JSON toggle** — view the full API response inline

---

## ⚙️ Environment Variables

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Your key from [console.groq.com](https://console.groq.com) |
| `API_KEY` | Secret key for endpoint auth (`mysecretkey123`) |
| `GOOGLE_CREDENTIALS_JSON` | Full JSON string from your GCP service account key file |
| `MC_RUNS` | Monte Carlo passes for small docs (default: `3`) |
| `CHUNK_SIZE` | Characters per chunk for large docs (default: `4000`) |
| `CHUNK_OVERLAP` | Overlap between chunks (default: `200`) |
| `CALL_DELAY` | Seconds between Groq calls to avoid rate limits (default: `3.0`) |

---

## 🧪 Running Tests Locally

### Unit tests (no API key required)
```bash
pytest tests/test_unit.py -v
```

### Full eval suite
```bash
# Against the live deployed URL
python tests/test_api.py --url https://buildbridgehackathon.onrender.com --key mysecretkey123
```

Results saved to `test_report.json` with per-test scoring breakdown.

---

## 🌍 Language Support

Google Vision API auto-detects the document language — no configuration needed. Supports 100+ languages including Tamil, Hindi, Telugu, Arabic, Chinese, Japanese, French, German and more. The API response (summary, entities, key points) is always returned in **English** regardless of the source document language. The `language` field in the response indicates what language the original document was written in.
