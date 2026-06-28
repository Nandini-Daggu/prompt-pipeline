# Prompt Pipeline — Bug Report Triage

Day 2 GenAI & Agentic AI Engineering homework.

A four-stage prompt-only pipeline that turns a raw bug report into a polished,
developer-ready triage ticket — with every stage visible in the browser.

---

## Quick Start

### 1. Create and activate a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set your OpenRouter API key

```bash
# Windows PowerShell
$env:OPENROUTER_API_KEY="sk-or-..."

# Windows CMD
set OPENROUTER_API_KEY=sk-or-...

# macOS / Linux
export OPENROUTER_API_KEY=sk-or-...
```

Get a free key at https://openrouter.ai

### 4. Run the app

```bash
python app.py
```

Open http://127.0.0.1:5000 in your browser.

---

## How to Use

1. Paste a bug report into the textarea (or click a sample button).
2. Pick a model from the dropdown.
3. Click **Run Pipeline**.
4. Each stage appears one after another with its prompt, raw LLM response, and parsed JSON.
5. The final triage ticket appears at the bottom.

---

## Pipeline Architecture

```
Raw Bug Report
     │
     ▼
┌─────────────────────────────────────────┐
│  Stage 1 — UNDERSTAND                   │
│  Technique: Role + Structured Output    │
│  Input:  raw text                       │
│  Output: 10-field JSON (title, env, …)  │
└─────────────────┬───────────────────────┘
                  │  JSON →
                  ▼
┌─────────────────────────────────────────┐
│  Stage 2 — REASON                       │
│  Technique: Chain of Thought            │
│  Input:  Stage 1 JSON                   │
│  Output: severity, root cause, fix JSON │
└─────────────────┬───────────────────────┘
                  │  JSON →
                  ▼
┌─────────────────────────────────────────┐
│  Stage 3 — PRODUCE                      │
│  Technique: Goal Oriented + Constraints │
│  Input:  Stage 1 + Stage 2 JSON         │
│  Output: 150–250 word triage ticket     │
└─────────────────┬───────────────────────┘
                  │  ticket text →
                  ▼
┌─────────────────────────────────────────┐
│  Stage 4 — CRITIQUE (stretch goal)      │
│  Technique: Self Check                  │
│  Input:  Stage 3 ticket                 │
│  Output: scores JSON; auto-redo if <7   │
└─────────────────────────────────────────┘
```

---

## Homework Requirements Mapping

| Requirement | Implementation |
|---|---|
| 3+ stages, each with named technique | 4 stages in `pipeline.py`, labeled on every card |
| Structured JSON handoff | Every stage returns JSON; next stage receives that exact JSON |
| Chain-of-thought (at least once) | Stage 2 uses explicit 5-step reasoning chain |
| Survive bad input | Stage 1 sets `parse_error`; Stage 3 opens with "(!) Incomplete report" |
| Glass, not black box | Every prompt, raw response, and parsed JSON visible in the UI |
| `parse_json` with retry | `parse_json()` in `pipeline.py` retries up to 2× on JSONDecodeError |
| `call_llm(prompt, model)` via Requests | Implemented in `pipeline.py`, reads `OPENROUTER_API_KEY` from env |
| Run on 3 inputs (incl. tricky) | Sample buttons: Normal Bug, Tricky Bug, Broken Input |
| Weakest link reflection | Stage 2 (REASON) — fix: RAG with past bug DB (Day 4) |
| Stage 4 self-check (stretch) | Scores completeness/actionability/clarity; rewrites if overall < 7 |

---

## File Structure

```
Prompt-pipeline/
├── app.py              Flask entry point
├── pipeline.py         All prompt logic (4 stages, call_llm, parse_json)
├── requirements.txt
├── README.md
├── templates/
│   └── index.html      Single-page UI
└── static/
    ├── style.css       Dark theme, color-coded stage cards
    └── script.js       Fetch /run, render results
```

---

## Weakest Link

**Stage 2 — REASON** is the weakest link. When the report is terse (no stack
trace, no component), the model must guess the root-cause category from minimal
signal and the suggested fix can degrade to "investigate logs."

- **How you'd know:** the `suggested_fix` field reads as a vague investigation
  step rather than a concrete code change.
- **Day 4 fix (RAG):** retrieve similar past bugs and their confirmed root
  causes from a vector store to ground the reasoning in real precedents.
- **Days 6–8 fix (tools):** let Stage 2 call a tool that fetches the relevant
  git diff or error-log tail — hard evidence instead of pattern-matching.
"# prompt-pipeline" 
