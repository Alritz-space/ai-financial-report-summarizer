# AI Financial Report Summarizer

> Upload a transaction CSV → click **Analyze** → get an executive-ready financial summary and a focused anomaly list.

## Problem

Financial analysts often spend hours reviewing transaction logs and financial statements before they can even begin writing an executive summary. This prototype automates that first pass.

The goal is not to replace a finance professional. It creates an **80%-done starting point** so a human reviewer can spend time on judgment, investigation, and decisions rather than blank-page drafting.

## What it does

1. Accepts a CSV containing `date`, `account`, `category`, `amount`, and `period`.
2. Parses the file in memory — no database.
3. Runs a rule-based anomaly detector:
   - compares each account's transactions with its historical distribution;
   - flags observations more than **2 standard deviations** from the account mean.
4. Sends compact parsed JSON plus the statistical flags to Gemini.
5. Gemini produces:
   - an approximately 150-word executive summary;
   - meaningful anomalies in structured JSON.
6. The backend merges statistical and LLM findings and de-duplicates overlapping flags.
7. The browser renders the result directly.

## Product approach

This deliberately uses **two layers**:

**Deterministic layer:** statistical rules make the system explainable and auditable.

**Generative layer:** Gemini interprets the numbers, turns patterns into plain English, reviews the rule flags, and notices additional patterns.

That division is intentional: the LLM is an analyst assistant, not the calculator of record.

## Architecture

```text
Browser
   │
   │ POST /analyze (CSV)
   ▼
FastAPI
   │
   ├── CSV validation + parsing
   ├── Rule-based anomaly detection
   │      └── >2σ account-level historical deviation
   │
   └── Compact JSON + rule flags
              │
              ▼
        Gemini Flash
              │
              └── structured JSON
                    ├── summary
                    └── anomalies
              │
              ▼
        Merge + de-duplicate
              │
              ▼
           Browser
```

## Tech stack

- **Frontend:** plain HTML, CSS, JavaScript
- **Backend:** FastAPI / Python
- **LLM:** Gemini Flash via `google-generativeai`
- **Data processing:** Python standard library
- **Deployment:** Render
- **Storage:** none; each upload is processed in memory

Google's current documentation also provides the newer `google-genai` SDK. This prototype intentionally follows the build specification's `google-generativeai` dependency so the implementation stays close to the requested portfolio architecture. citeturn0search2turn0search1

## Structured output

The Gemini request uses JSON MIME output plus a response schema rather than relying on prompt-only JSON instructions. Google's Gemini API documentation supports this pattern for structured JSON generation. citeturn0search1

## Prompt

The full system prompt is intentionally visible at:

`prompts/summarizer_prompt.txt`

This makes the AI behavior easy to inspect, explain in an interview, and tune without burying the product logic inside application code.

## Sample data

`sample_data.csv` contains synthetic transactions covering four quarters of a fictional mid-size company.

It deliberately includes a few unusual events so the demo produces useful results:

- Travel expense spike
- Cloud infrastructure spike
- Professional services credit
- Marketing spike

No real company data is used.

## Run locally

### 1. Create an environment

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set the Gemini API key

Copy `.env.example` to `.env` or export the variables in your shell:

```text
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

The app reads environment variables directly. For local `.env` loading, use your preferred environment loader or export the variables in the shell.

### 4. Start the app

```bash
uvicorn app:app --reload
```

Open:

`http://localhost:8000`

### 5. Run tests

```bash
pytest
```

## Deploy on Render

1. Push this repository to GitHub.
2. In Render, create a new **Web Service** from the GitHub repository.
3. Render can use the included `render.yaml`.
4. Add `GEMINI_API_KEY` as a Render environment variable.
5. Deploy.
6. Connect the repository so pushes to `main` trigger automatic redeploys.

**Important:** never commit the Gemini API key.

Render's free service can sleep after inactivity, so the first request after a quiet period may take roughly 30–60 seconds. For an interview, open the URL a few minutes beforehand.

## Demo script — 60–90 seconds

**0–10 sec:** "This is an AI financial report summarizer. The problem is that analysts spend too much time turning transaction data into the first executive draft."

**10–25 sec:** Upload `sample_data.csv`.

**25–40 sec:** Click **Analyze**. Explain that the backend first runs a deterministic 2-standard-deviation anomaly check, then sends compact JSON and those flags to Gemini.

**40–60 sec:** Read the executive summary. Point out that the language is aimed at a non-financial executive rather than an accountant.

**60–75 sec:** Show the anomaly list. Explain that the LLM reviews statistical flags and can add patterns such as abrupt quarter changes or unusual credits.

**75–90 sec:** "The important product decision is that AI is not the only detection mechanism. The statistical layer gives us an explainable control, while the LLM provides interpretation."

## What I'd build next

If this moved beyond a portfolio prototype:

1. **Explainability panel** — show the historical baseline, z-score, and transactions behind each flag.
2. **Human review workflow** — accept, dismiss, or investigate each anomaly.
3. **Period-aware baselines** — compare Q4 to prior Q4s instead of treating all periods equally.
4. **Materiality thresholds** — combine statistical unusualness with dollar materiality.
5. **Financial statement context** — connect transaction-level anomalies to P&L and balance-sheet impact.
6. **Audit trail** — preserve prompt version, model version, input hash, and reviewer decision.
7. **Role-specific summaries** — CFO, controller, FP&A, and business-unit views.
8. **Trend visualizations** — category and account movements over time.
9. **Cloud Run option** — move from Render if a no-sleep experience becomes important.

## Portfolio positioning

This project demonstrates a practical **AI + ERP product pattern**:

> **Rules for control. AI for interpretation. Humans for judgment.**

It is intentionally small enough to demo in under two minutes, while still showing product thinking around trust, explainability, structured outputs, and human-in-the-loop review.
