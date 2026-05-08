# CohortFilter AI — Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER (Program Manager)                      │
│                    Browser @ http://localhost:8000                   │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FRONTEND (Vanilla HTML/CSS/JS)                    │
│                                                                     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────┐  │
│  │   Rubric   │  │    CSV     │  │  Results   │  │    Export     │  │
│  │    Chat    │  │   Upload   │  │ Dashboard  │  │  (PDF/CSV)   │  │
│  └────────────┘  └────────────┘  └────────────┘  └──────────────┘  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │  REST API (fetch)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    BACKEND (Python / FastAPI)                        │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    API Layer (main.py)                        │   │
│  │                                                              │   │
│  │  POST /api/chat          — Rubric extraction (NLP)           │   │
│  │  POST /api/rubric        — Save rubric config                │   │
│  │  POST /api/upload        — Upload CSV                        │   │
│  │  POST /api/score/{id}    — Start async scoring job           │   │
│  │  GET  /api/jobs/{id}     — Poll job status + progress        │   │
│  │  GET  /api/export/pdf    — Download shortlist PDF            │   │
│  │  GET  /api/export/csv    — Download scored CSV               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │   Scoring    │  │  Duplicate   │  │     PDF Export           │  │
│  │   Pipeline   │  │  Detector    │  │    (ReportLab)           │  │
│  │ (scoring.py) │  │(difflib sim) │  │   (pdf_export.py)       │  │
│  └──────┬───────┘  └──────────────┘  └──────────────────────────┘  │
│         │                                                           │
│  ┌──────▼───────┐  ┌──────────────┐                                │
│  │  LLM Adapter │  │   Storage    │                                │
│  │              │  │ (JSON/SQLite │                                │
│  │ mock/openai/ │  │  + MindsDB)  │                                │
│  │    vllm      │  │ (storage.py) │                                │
│  └──────┬───────┘  └──────────────┘                                │
└─────────┼──────────────────────────────────────────────────────────┘
          │  OpenAI-compatible API
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│              AMD DEVELOPER CLOUD (MI300X Instance)                   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    vLLM Inference Server                      │   │
│  │                                                              │   │
│  │  Model: meta-llama/Llama-3-70b-instruct (or 8b for dev)     │   │
│  │  GPU:   AMD Instinct MI300X (192GB HBM3)                    │   │
│  │  Stack: ROCm 6.x + PyTorch + vLLM                           │   │
│  │  API:   OpenAI-compatible (http://<ip>:8000/v1)              │   │
│  │                                                              │   │
│  │  Features:                                                   │   │
│  │  - PagedAttention for memory-efficient KV cache              │   │
│  │  - Continuous batching for high throughput                   │   │
│  │  - Structured JSON output via temperature=0.1                │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
1. RUBRIC SETUP
   User message ──▶ /api/chat ──▶ NLP extraction ──▶ RubricConfig ──▶ storage

2. CSV UPLOAD
   CSV file ──▶ /api/upload ──▶ parse rows ──▶ store by upload_id

3. SCORING (async job)
   /api/score ──▶ create job ──▶ for each application:
                                   │
                                   ├──▶ build_scoring_prompt()
                                   ├──▶ LLM adapter (mock/openai/vllm)
                                   ├──▶ parse JSON response
                                   ├──▶ apply dealbreaker rules
                                   └──▶ update progress
                                │
                                ├──▶ sort by total_score (desc)
                                ├──▶ assign ranks
                                ├──▶ detect_duplicates() (difflib)
                                └──▶ store results

4. EXPORT
   /api/export/pdf ──▶ ReportLab ──▶ branded A4 PDF
   /api/export/csv ──▶ flatten scores ──▶ CSV download
```

## LLM Adapter Modes

```
┌─────────────────────────────────────────────────┐
│            LLM_MODE Environment Variable         │
├─────────┬───────────────────────────────────────┤
│  mock   │ Keyword heuristics, no API call       │
│         │ 150-400ms per application             │
│         │ Used for development and demo fallback│
├─────────┼───────────────────────────────────────┤
│  openai │ Standard OpenAI API                   │
│         │ Any model (gpt-4o, gpt-3.5-turbo)     │
│         │ Used for local dev testing             │
├─────────┼───────────────────────────────────────┤
│  vllm   │ vLLM on AMD Developer Cloud           │
│         │ Llama 3 8B/70B on MI300X               │
│         │ Production inference endpoint          │
└─────────┴───────────────────────────────────────┘

All modes use the same OpenAI-compatible API format.
Switching requires only changing environment variables — zero code changes.
```

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **Async job-based scoring** | Prevents HTTP timeouts, enables progress tracking, scales to 1000+ rows |
| **Mock-first adapter** | Product development not blocked by GPU provisioning |
| **Server-side PDF** | ReportLab produces clean, consistent A4 output vs brittle client-side rendering |
| **difflib for duplicates** | Zero-dependency, fast pairwise comparison; LLM only for explanation (future) |
| **JSON/SQLite fallback** | MindsDB is enhancement, not critical path; reduces hackathon risk |
| **Structured JSON prompts** | Forces consistent LLM output; eliminates freeform parsing failures |
