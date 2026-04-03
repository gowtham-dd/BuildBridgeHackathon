# DocuSense — AI Document Analyzer API

> **Hackathon Track 2** · FastAPI · Groq LLaMA-3-8B-Instant · Monte Carlo consensus · EasyOCR + Tesseract · PyMuPDF · python-docx

---

## 🚀 Live Demo
- **API:** `https://your-app.onrender.com/api/document-analyze`
- **Web UI:** `https://your-app.onrender.com/`

---

## 📐 Architecture & Approach

```
Request (PDF/DOCX/Image base64)
        │
        ▼
┌──────────────────────┐
│   Auth Middleware    │  x-api-key header validation
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Extraction Layer    │  PDF → PyMuPDF (layout-preserving)
│                      │  DOCX → python-docx (.doc auto-converted via LibreOffice)
│                      │  Image → EasyOCR (deep learning) → Tesseract (fallback)
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│               Monte Carlo AI Pipeline                        │
│                                                              │
│  5 parallel Groq LLaMA-3-8B-Instant calls                   │
│  Temperature ladder: [0.0, 0.1, 0.2, 0.3, 0.4]             │
│                                                              │
│  Aggregation:                                                │
│    summary   → longest / most detailed response             │
│    sentiment → majority vote across 5 runs                  │
│    entities  → consensus: items in ≥ 3/5 runs               │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
    Structured JSON response
```

### Why Monte Carlo?
Single LLM calls are stochastic. By running multiple passes at varying temperatures:
- **Sentiment** is determined by majority vote → reduces single-pass hallucination
- **Entities** are deduplicated and consensus-filtered → only confirmed entities survive
- **Summary** uses the most detailed successful output

---

## 📦 Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI + Uvicorn |
| LLM | Groq · `llama-3-1-8b-instant` |
| LLM Orchestration | LangChain + langchain-groq |
| PDF Extraction | PyMuPDF (fitz) — layout preserving |
| DOCX Extraction | python-docx |
| .doc Conversion | LibreOffice headless |
| Image OCR | EasyOCR (primary) · Tesseract (fallback) |
| Validation | Pydantic v2 |

---

## 📁 Project Structure

```
doc-analyzer/
├── main.py                    # FastAPI app entry point
├── requirements.txt
├── .env.example
│
├── routers/
│   └── analyze.py             # POST /api/document-analyze
│
├── models/
│   ├── request.py             # AnalyzeRequest schema
│   ├── response.py            # AnalyzeResponse schema
│   └── entities.py            # EntitiesModel sub-schema
│
├── services/
│   ├── extractor.py           # PDF / DOCX / Image extraction
│   └── ai_pipeline.py         # Monte Carlo LLM orchestration
│
├── prompts/
│   └── analysis_prompt.py     # System + user prompt builders
│
└── static/
    └── index.html             # Web UI (Chart.js visualizations)
```

---

## ⚙️ Setup & Run

### 1. Clone & install

```bash
git clone https://github.com/your-handle/doc-analyzer.git
cd doc-analyzer
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. System dependencies

```bash
# Ubuntu/Debian
sudo apt-get install -y tesseract-ocr libreoffice

# macOS
brew install tesseract libreoffice
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set:
#   GROQ_API_KEY=your_key_from_console.groq.com
#   API_KEY=any_secret_key_you_choose
```

### 4. Run

```bash
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000` for the Web UI.  
API docs at `http://localhost:8000/docs`.

---

## 🔌 API Reference

### `POST /api/document-analyze`

**Headers**
```
Content-Type: application/json
x-api-key: your_api_key
```

**Request Body**
```json
{
  "fileName": "invoice.pdf",
  "fileType": "pdf",
  "fileBase64": "<base64-encoded file content>"
}
```

`fileType` must be one of: `"pdf"` | `"docx"` | `"image"`

**Response**
```json
{
  "status": "success",
  "fileName": "invoice.pdf",
  "summary": "This document is an invoice from Acme Corp...",
  "entities": {
    "names": ["John Smith"],
    "dates": ["2024-01-15", "Q1 2024"],
    "organizations": ["Acme Corp", "Tech Solutions Ltd"],
    "amounts": ["$12,500.00", "15%"],
    "locations": ["New York, NY", "San Francisco"]
  },
  "sentiment": "neutral"
}
```

**Error responses**

| Code | Meaning |
|---|---|
| 401 | Invalid or missing x-api-key |
| 422 | No text could be extracted |
| 500 | Internal server error |

---

## ☁️ Deploy to Render

1. Push to GitHub
2. Create a new **Web Service** on [render.com](https://render.com)
3. Set **Build Command:** `pip install -r requirements.txt`
4. Set **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables: `GROQ_API_KEY`, `API_KEY`

> ⚠️ Render free tier may need system packages. Add a `render.yaml`:
> ```yaml
> services:
>   - type: web
>     name: doc-analyzer
>     runtime: python
>     buildCommand: apt-get install -y tesseract-ocr libreoffice && pip install -r requirements.txt
>     startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
>     envVars:
>       - key: GROQ_API_KEY
>         sync: false
>       - key: API_KEY
>         sync: false
> ```

---

## 🧪 Testing

### Unit tests (offline — no API key required)
```bash
pytest tests/test_unit.py -v
```
Tests cover: Monte Carlo aggregation, majority vote, entity casing, JSON parsing, truncation, and extractor helpers.

### Hackathon eval suite (15 cases, 100 pts)
```bash
# With local server running:
python tests/test_api.py --url http://localhost:8000 --key your_api_key

# Against deployed URL:
python tests/test_api.py --url https://your-app.onrender.com --key your_api_key
```

Scoring breakdown per test:
- **Summary** — 2 pts: length check + keyword coverage
- **Entities** — 4 pts: minimum counts per category (names/dates/orgs/amounts/locations)
- **Sentiment** — 4 pts: exact match

Results are saved to `test_report.json` with full per-test breakdown.

### Quick curl test
```bash
B64=$(base64 -w 0 my_document.pdf)

curl -X POST http://localhost:8000/api/document-analyze \
  -H "Content-Type: application/json" \
  -H "x-api-key: your_api_key" \
  -d "{\"fileName\":\"my_document.pdf\",\"fileType\":\"pdf\",\"fileBase64\":\"$B64\"}"
```

---

## 📁 Full Project Structure

```
doc-analyzer/
├── main.py                    # FastAPI app entry point
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variable template
├── Dockerfile                 # Container build (includes Tesseract + LibreOffice)
├── render.yaml                # One-click Render.com deployment
├── pytest.ini                 # Test configuration
├── README.md
│
├── routers/
│   └── analyze.py             # POST /api/document-analyze + auth middleware
│
├── models/
│   ├── request.py             # AnalyzeRequest (fileName, fileType, fileBase64)
│   ├── response.py            # AnalyzeResponse (status, fileName, summary, entities, sentiment)
│   └── entities.py            # EntitiesModel (names, dates, organizations, amounts, locations)
│
├── services/
│   ├── extractor.py           # PDF (PyMuPDF) / DOCX (python-docx) / Image (EasyOCR→Tesseract)
│   └── ai_pipeline.py         # Monte Carlo LLM orchestration + aggregation
│
├── prompts/
│   └── analysis_prompt.py     # System + user prompt builders (isolated for tuning)
│
├── static/
│   └── index.html             # Web UI with Chart.js doughnut + bar charts
│
└── tests/
    ├── test_unit.py           # Offline unit tests (aggregation, parsing, extraction)
    └── test_api.py            # 15-case hackathon eval suite with scoring
```
