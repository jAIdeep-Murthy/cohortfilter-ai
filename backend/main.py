"""CohortFilter AI — FastAPI backend.

Endpoints:
  POST /api/rubric         — Save rubric configuration
  GET  /api/rubric         — Get current rubric
  POST /api/chat           — Rubric chat (mock NLP extraction)
  POST /api/upload         — Upload CSV of applications
  POST /api/score/{id}     — Start async scoring job
  GET  /api/jobs/{id}      — Poll job status / progress
  GET  /api/export/pdf/{id}— Download shortlist PDF
  GET  /api/export/csv/{id}— Download scored CSV
  GET  /api/demo/csv       — Get built-in demo CSV
"""

import asyncio
import csv
import io
import json
import os
import re
import uuid
from datetime import datetime, timezone

import pypdf
import docx

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from models import RubricConfig, ChatRequest, Dealbreaker, RubricDimension
from storage import Storage
from scoring import run_scoring_pipeline
from pdf_export import generate_shortlist_pdf

app = FastAPI(title="CohortFilter AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = Storage()
jobs = {}  # job_id -> job state dict

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


# ── Serve frontend ──────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# Mount static files AFTER the root route
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ── Rubric endpoints ────────────────────────────────────────

@app.post("/api/rubric")
async def save_rubric(config: RubricConfig):
    storage.save_rubric(config)
    return {"status": "ok", "rubric": config.model_dump()}


@app.get("/api/rubric")
async def get_rubric():
    rubric = storage.get_rubric()
    if rubric:
        return rubric.model_dump()
    return None


@app.post("/api/chat")
async def rubric_chat(req: ChatRequest):
    """Mock NLP: extract rubric parameters from natural language."""
    msg = req.message.lower()

    # Extract program focus
    focus_parts = []
    if any(kw in msg for kw in ["ai", "artificial intelligence", "ml", "machine learning"]):
        focus_parts.append("AI/ML-focused")
    if any(kw in msg for kw in ["fintech", "finance"]):
        focus_parts.append("Fintech")
    if any(kw in msg for kw in ["health", "biotech", "medtech"]):
        focus_parts.append("HealthTech")
    if any(kw in msg for kw in ["india", "indian"]):
        focus_parts.append("India-based")
    if any(kw in msg for kw in ["southeast asia", "sea", "singapore"]):
        focus_parts.append("Southeast Asia")
    if any(kw in msg for kw in ["pre-seed", "preseed"]):
        focus_parts.append("Pre-seed stage")
    if any(kw in msg for kw in ["seed", "series a"]):
        focus_parts.append("Seed stage")
    program_focus = ", ".join(focus_parts) if focus_parts else "General accelerator program"

    # Extract dealbreakers
    dealbreakers = []
    if any(kw in msg for kw in ["no solo", "solo founder", "single founder"]):
        dealbreakers.append(Dealbreaker(rule="No solo founders", field_hint="team_size"))
    mrr_match = re.search(r"\$?([\d,]+)\s*k?\+?\s*mrr", msg)
    if mrr_match:
        val = mrr_match.group(1).replace(",", "")
        dealbreakers.append(Dealbreaker(rule=f"Must have ${val}K+ MRR", field_hint="mrr"))
    if "revenue" in msg and ("must" in msg or "require" in msg):
        dealbreakers.append(Dealbreaker(rule="Must have revenue", field_hint="mrr"))

    # Extract scoring dimensions and weights
    dimensions = []
    dim_patterns = [
        (r"traction\s*(?:[\-:=])?\s*(\d+)\s*%", "Traction"),
        (r"team\s*(?:strength|quality)?\s*(?:[\-:=])?\s*(\d+)\s*%", "Team"),
        (r"market\s*(?:fit|size|opportunity)?\s*(?:[\-:=])?\s*(\d+)\s*%", "Market Fit"),
        (r"mission\s*(?:alignment|fit)?\s*(?:[\-:=])?\s*(\d+)\s*%", "Mission Alignment"),
        (r"innovation\s*(?:[\-:=])?\s*(\d+)\s*%", "Innovation"),
        (r"product\s*(?:[\-:=])?\s*(\d+)\s*%", "Product"),
    ]
    for pattern, name in dim_patterns:
        m = re.search(pattern, msg)
        if m:
            weight = int(m.group(1)) / 100.0
            dimensions.append(RubricDimension(
                name=name, weight=weight,
                description=f"Score the {name.lower()} of the startup"
            ))

    # Defaults if nothing extracted
    if not dimensions:
        dimensions = [
            RubricDimension(name="Traction", weight=0.35, description="Revenue, users, growth metrics, market validation"),
            RubricDimension(name="Team", weight=0.30, description="Team size, experience, technical capability, commitment"),
            RubricDimension(name="Market Fit", weight=0.20, description="Market size, timing, competitive positioning"),
            RubricDimension(name="Mission Alignment", weight=0.15, description="Alignment with program thesis and focus areas"),
        ]

    rubric = RubricConfig(
        program_focus=program_focus,
        dealbreakers=dealbreakers,
        dimensions=dimensions,
    )

    # Build response message
    dim_text = "\n".join(f"  • **{d.name}** — {d.weight:.0%}" for d in dimensions)
    db_text = "\n".join(f"  • {d.rule}" for d in dealbreakers) if dealbreakers else "  • None specified"

    response = f"""I've configured your scoring rubric:

**Program Focus:** {program_focus}

**Scoring Dimensions:**
{dim_text}

**Dealbreakers:**
{db_text}

Does this look right? Click **Confirm Rubric** to proceed to data upload."""

    return {
        "response": response,
        "rubric": rubric.model_dump(),
    }

@app.post("/api/chat/document")
async def upload_rubric_document(file: UploadFile = File(...)):
    """Extract rubric from an uploaded document (PDF, DOCX, TXT) using LLM."""
    from llm_adapter import extract_rubric_with_llm
    
    ext = os.path.splitext(file.filename)[1].lower()
    content = await file.read()
    
    text = ""
    try:
        if ext in [".txt", ".md", ".csv"]:
            text = content.decode("utf-8")
        elif ext == ".pdf":
            reader = pypdf.PdfReader(io.BytesIO(content))
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        elif ext in [".doc", ".docx"]:
            doc = docx.Document(io.BytesIO(content))
            text = "\n".join([p.text for p in doc.paragraphs])
        else:
            raise HTTPException(400, f"Unsupported file type: {ext}. Please upload a PDF, DOCX, or TXT.")
    except Exception as e:
        raise HTTPException(400, f"Error reading document: {str(e)}")
        
    if not text.strip():
        raise HTTPException(400, "The document appears to be empty or unreadable.")
        
    try:
        rubric_dict = await extract_rubric_with_llm(text)
        
        # Ensure it has the right shape
        rubric = RubricConfig(
            program_focus=rubric_dict.get("program_focus", "General accelerator"),
            dimensions=[RubricDimension(**d) for d in rubric_dict.get("dimensions", [])],
            dealbreakers=[Dealbreaker(**d) for d in rubric_dict.get("dealbreakers", [])],
        )
        
        dim_text = "\n".join(f"  • **{d.name}** — {d.weight:.0%}" for d in rubric.dimensions)
        db_text = "\n".join(f"  • {d.rule}" for d in rubric.dealbreakers) if rubric.dealbreakers else "  • None specified"

        response = f"""I successfully processed your document: **{file.filename}** and extracted your rubric:

**Program Focus:** {rubric.program_focus}

**Scoring Dimensions:**
{dim_text}

**Dealbreakers:**
{db_text}

Does this look right? Click **Confirm Rubric** to proceed to data upload."""

        return {
            "response": response,
            "rubric": rubric.model_dump(),
        }
    except Exception as e:
        raise HTTPException(500, f"Error processing document with AI: {str(e)}")

# ── Upload endpoint ─────────────────────────────────────────

@app.post("/api/upload")
async def upload_csv(file: UploadFile = File(...)):
    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        raise HTTPException(400, "CSV is empty")

    upload_id = str(uuid.uuid4())[:8]
    storage.save_applications(upload_id, rows)

    return {
        "upload_id": upload_id,
        "row_count": len(rows),
        "columns": list(rows[0].keys()) if rows else [],
        "sample": rows[:3],
    }


# ── Scoring endpoints ───────────────────────────────────────

@app.post("/api/score/{upload_id}")
async def start_scoring(upload_id: str):
    applications = storage.get_applications(upload_id)
    if not applications:
        raise HTTPException(404, "Upload not found")

    rubric = storage.get_rubric()
    if not rubric:
        raise HTTPException(400, "No rubric configured. Please set up rubric first.")

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
        "progress": 0,
        "total": len(applications),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "results": None,
        "duplicates": [],
        "error": None,
    }

    # Run in background
    asyncio.create_task(_execute_scoring_job(job_id, upload_id, applications, rubric))

    return {"job_id": job_id, "status": "running", "total": len(applications)}


async def _execute_scoring_job(job_id, upload_id, applications, rubric):
    """Background task that runs the scoring pipeline."""
    async def on_progress(current, total):
        jobs[job_id]["progress"] = current

    try:
        results, duplicates = await run_scoring_pipeline(
            applications, rubric, progress_callback=on_progress
        )
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["results"] = results
        jobs[job_id]["duplicates"] = duplicates
        jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
        storage.save_results(upload_id, job_id, results)
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    job = jobs[job_id]
    # Don't send full results in status poll (too large); send summary
    response = {
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": job["progress"],
        "total": job["total"],
        "started_at": job["started_at"],
        "completed_at": job["completed_at"],
        "error": job["error"],
    }
    if job["status"] == "completed":
        response["results"] = job["results"]
        response["duplicates"] = job["duplicates"]
    return response


# ── Export endpoints ─────────────────────────────────────────

@app.get("/api/export/pdf/{job_id}")
async def export_pdf(job_id: str, top_n: int = Query(default=10, ge=1, le=100)):
    if job_id not in jobs or jobs[job_id]["status"] != "completed":
        raise HTTPException(404, "Results not available")

    results = jobs[job_id]["results"]
    rubric = storage.get_rubric()
    shortlist = results[:top_n]

    pdf_bytes = generate_shortlist_pdf(shortlist, rubric)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=cohortfilter_shortlist_{job_id}.pdf"
        },
    )


@app.get("/api/export/csv/{job_id}")
async def export_csv(job_id: str):
    if job_id not in jobs or jobs[job_id]["status"] != "completed":
        raise HTTPException(404, "Results not available")

    results = jobs[job_id]["results"]
    output = io.StringIO()

    if results:
        # Flatten for CSV
        flat_keys = ["rank", "startup_name", "founder_name", "total_score",
                     "confidence", "summary", "risk_flags", "website_status",
                     "dealbreaker_hit", "dealbreaker_reason"]
        # Add dimension columns
        if results[0].get("dimension_scores"):
            for dim_name in results[0]["dimension_scores"]:
                flat_keys.append(f"{dim_name}_score")
                flat_keys.append(f"{dim_name}_reason")

        writer = csv.DictWriter(output, fieldnames=flat_keys)
        writer.writeheader()
        for r in results:
            row = {
                "rank": r.get("rank", ""),
                "startup_name": r.get("startup_name", ""),
                "founder_name": r.get("founder_name", ""),
                "total_score": r.get("total_score", ""),
                "confidence": r.get("confidence", ""),
                "summary": r.get("summary", ""),
                "risk_flags": "; ".join(r.get("risk_flags", [])),
                "website_status": r.get("website_status", ""),
                "dealbreaker_hit": r.get("dealbreaker_hit", ""),
                "dealbreaker_reason": r.get("dealbreaker_reason", ""),
            }
            for dim_name, dim_data in r.get("dimension_scores", {}).items():
                row[f"{dim_name}_score"] = dim_data.get("score", "")
                row[f"{dim_name}_reason"] = dim_data.get("reason", "")
            writer.writerow(row)

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=cohortfilter_scored_{job_id}.csv"
        },
    )


# ── Demo data ───────────────────────────────────────────────

@app.get("/api/demo/csv")
async def get_demo_csv():
    demo_path = os.path.join(DATA_DIR, "demo_applications.csv")
    if os.path.exists(demo_path):
        return FileResponse(demo_path, media_type="text/csv", filename="demo_applications.csv")
    raise HTTPException(404, "Demo CSV not found")


# ── Run ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
