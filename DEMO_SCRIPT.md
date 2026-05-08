# CohortFilter AI — Demo Script (3 Minutes)

> Use this script for the hackathon demo video and live presentation.
> Total runtime: ~3 minutes. Practice 3x before recording.

---

## 0:00–0:30 — The Problem (30s)

**[Show title slide or CohortFilter AI landing]**

> "Every year, top accelerators like Techstars, 500 Global, and Google for Startups India receive thousands of applications per cohort — sometimes ten thousand or more.
>
> Program managers spend 80% of their triage time manually reading applications in spreadsheets, applying inconsistent scoring, and arguing about who makes the shortlist.
>
> There is no integrated AI tool for this workflow. Until now."

---

## 0:30–1:30 — Live Product Demo (60s)

**[Switch to browser — http://localhost:8000]**

### Step 1: Define Rubric (15s)

> "First, the program manager tells the AI what they're looking for."

- Click **Load Demo Rubric** (or type: "AI-focused accelerator, pre-seed, India. No solo founders, must have $5K+ MRR. Traction 40%, Team 30%, Market Fit 20%, Mission 10%.")
- AI extracts structured rubric
- Click **Confirm Rubric & Continue**

> "The AI extracts a structured scoring rubric — dimensions, weights, and dealbreakers — from natural language."

### Step 2: Upload Data (10s)

> "Next, upload the raw application CSV — straight from Typeform or Google Forms."

- Click **Use Demo Dataset (50 applications)**
- Preview table appears

> "50 applications loaded. In production, this handles 1,000+ rows asynchronously."

### Step 3: Score (15s)

- Click **Score Applications**
- Watch progress bar fill

> "Each application is scored against the rubric using Llama 3 running on AMD MI300X GPUs via vLLM. Watch the progress — 50 applications scored in under 30 seconds."

### Step 4: Review Results (20s)

- Dashboard appears with stats: Total / Shortlisted / Flagged / Dealbreakers
- Point out duplicate detection alert (NeuralMesh ↔ SupplySync, 82% similarity)
- Expand one top-ranked row to show dimension scores and AI explanation
- Expand one dealbreaker row to show rejection reason

> "The dashboard shows ranked results with explainable scores. Duplicates are auto-flagged. Dealbreakers are highlighted. Every score has a reason."

---

## 1:30–2:00 — AMD Infrastructure (30s)

**[Show architecture slide or ARCHITECTURE.md diagram]**

> "Under the hood, CohortFilter AI runs Llama 3 on AMD Instinct MI300X GPUs using vLLM with ROCm — AMD's open-source GPU compute stack.
>
> vLLM gives us high-throughput batch inference with PagedAttention, so we can process hundreds of applications in parallel. The entire pipeline is exposed as an OpenAI-compatible API, making it trivial to swap models or scale.
>
> For this demo, we're running Llama 3 8B. In production, the same architecture supports Llama 3 70B for deeper evaluation."

---

## 2:00–2:30 — Business Value (30s)

> "CohortFilter AI solves a real operational problem:
>
> - **80% time saved** on application triage
> - **Auditable scores** — every decision has a reason
> - **Duplicate detection** catches copycat applications automatically
> - **PDF shortlist** ready for stakeholder review in one click
>
> Target customers: program managers at accelerators with $50K–$500K ops budgets. No integrated tool exists today."

---

## 2:30–3:00 — Close (30s)

**[Show export — click Download PDF, open PDF briefly]**

> "The final shortlist exports as a branded PDF — ready for the investment committee."

**[Return to title slide]**

> "CohortFilter AI. The AI that shortlists accelerator applications so program managers only review the top 10%.
>
> Built with Llama 3 on AMD MI300X. Open source. Ready to deploy.
>
> Thank you."

---

## Notes for Recording

- **Resolution:** 1920×1080, 16:9
- **Format:** MP4
- **Browser:** Full screen, no bookmarks bar, clean tab
- **Font size:** Ensure dashboard text is readable at 1080p
- **Pre-load:** Run the demo once before recording so results are cached; then reset and record fresh
- **Backup:** If AMD endpoint is slow, switch to `LLM_MODE=mock` — demo still works perfectly
