"""
pipeline.py — Bug Report Triage prompt pipeline (4 stages, no frameworks).

Stage 1  UNDERSTAND   role + structured_output
Stage 2  REASON       chain_of_thought
Stage 3  PRODUCE      goal_oriented + constraints
Stage 4  CRITIQUE     self_check
"""

import json
import os
import re
import time

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

def call_llm(prompt: str, model: str) -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY environment variable is not set.")
    resp = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# JSON parser with retry
# ---------------------------------------------------------------------------

def _extract_brace_block(text: str) -> str:
    """Return the first brace-balanced JSON object from text."""
    start = text.find("{")
    if start == -1:
        return text
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if esc:
            esc = False
        elif ch == "\\" and in_str:
            esc = True
        elif ch == '"':
            in_str = not in_str
        elif not in_str:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return text[start:]


def parse_json(raw: str, original_prompt: str, model: str, max_retries: int = 2) -> dict:
    for attempt in range(max_retries):
        candidate = _extract_brace_block(raw)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as err:
            if attempt + 1 == max_retries:
                raise ValueError(
                    f"JSON parse failed after {max_retries} attempts: {err}\nRaw output:\n{raw}"
                )
            # Re-ask with the error context
            raw = call_llm(
                f"{original_prompt}\n\n"
                f"Your previous response could not be parsed as JSON.\n"
                f"Parse error: {err}\n"
                f"Bad output:\n{raw}\n\n"
                "Return ONLY valid JSON — no prose, no markdown fences.",
                model,
            )


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

PROMPT1 = """\
You are a senior QA engineer specialising in bug triage.
Your task: read the raw bug report below and extract every relevant fact into structured JSON.

Bug report:
\"\"\"
{text}
\"\"\"

Rules:
- Use null for any field you cannot determine from the text.
- If the report is non-English, translate field values to English.
- If the report is gibberish or contains no usable information, set "parse_error" to a short explanation and all other fields to null.
- Return ONLY valid JSON — no prose, no markdown fences, no code block markers.

Required JSON schema (return exactly this structure):
{{
  "title": "<one-line summary of the bug>",
  "component": "<affected module or service, or null>",
  "environment": "<OS / browser / version, or null>",
  "steps_to_reproduce": ["<step 1>", "<step 2>"],
  "expected_behaviour": "<what should happen>",
  "actual_behaviour": "<what actually happens>",
  "error_message": "<exact error text or exception, or null>",
  "stack_trace": "<condensed stack trace, or null>",
  "reporter_sentiment": "frustrated | neutral | calm",
  "parse_error": null
}}"""


PROMPT2 = """\
You are a principal engineer performing root-cause analysis on a structured bug brief.
Think step by step — reason explicitly before committing to any answer.

Structured bug brief (JSON from Stage 1):
{brief}

Reasoning instructions — work through these steps before answering:
Step 1: Identify the most likely root-cause category:
        null_pointer | race_condition | config_error | dependency_version |
        logic_bug | network_timeout | auth_failure | unknown
Step 2: Assess severity:
        P0 = system completely down
        P1 = major feature broken, no workaround
        P2 = minor degradation, workaround exists
        P3 = cosmetic / low impact
Step 3: Propose ONE concrete fix (a code change, config tweak, or specific investigation step).
Step 4: Assign an owner team: frontend | backend | infra | data | qa | unknown
Step 5: Estimate fix effort: trivial (<1 h) | small (1–4 h) | medium (1–2 d) | large (>2 d)

After reasoning, return ONLY valid JSON — no prose, no markdown fences:
{{
  "reasoning_chain": [
    "Step 1: ...",
    "Step 2: ...",
    "Step 3: ...",
    "Step 4: ...",
    "Step 5: ..."
  ],
  "root_cause_category": "<category>",
  "root_cause_explanation": "<1–2 sentences>",
  "severity": "P0|P1|P2|P3",
  "suggested_fix": "<concrete actionable fix>",
  "owner_team": "<team>",
  "fix_effort": "trivial|small|medium|large"
}}"""


PROMPT3 = """\
You are a technical writer producing a developer-ready bug triage ticket.

Bug brief from Stage 1 (JSON):
{brief}

Engineering analysis from Stage 2 (JSON):
{decision}

Write a triage ticket following ALL these constraints:
- Start with a heading: ## [SEVERITY] Title  (e.g. ## [P1] Login crashes on timeout)
- Include exactly these sections in order:
    **Summary** — 2–3 sentences describing the bug and its impact.
    **Steps to Reproduce** — numbered list.
    **Root Cause** — what went wrong and why.
    **Suggested Fix** — a concrete, actionable fix a developer can implement.
    **Owner & Effort** — team name and time estimate.
- Total length: 150–250 words.
- Tone: precise, professional, no filler phrases ("it seems", "apparently", etc.).
- If parse_error is set in the brief, open with: "(!) Incomplete report — " and note what is missing.
- Return plain text only — no JSON, no code fences."""


PROMPT4 = """\
You are a quality reviewer grading an engineering triage ticket.

Ticket to review:
\"\"\"
{ticket}
\"\"\"

Grade each criterion from 0 to 10:
1. Completeness — are all required sections present and filled?
2. Actionability — is the suggested fix specific enough for a developer to act on?
3. Clarity — is it precise, unambiguous, and free of filler?

Rules:
- overall = average of the three scores, rounded to 1 decimal place.
- passed = true if overall >= 7.0, false otherwise.
- If passed is false, write an improved version of the ticket in "revised_ticket"
  following the same format constraints as the original prompt.
- If passed is true, set "revised_ticket" to null.
- Return ONLY valid JSON — no prose, no markdown fences:

{{
  "scores": {{
    "completeness": 0,
    "actionability": 0,
    "clarity": 0
  }},
  "overall": 0.0,
  "passed": true,
  "feedback": "<one sentence — what to improve, or 'Looks good.' if passed>",
  "revised_ticket": null
}}"""


# ---------------------------------------------------------------------------
# Stage functions
# ---------------------------------------------------------------------------

def stage1_understand(text: str, model: str) -> tuple[dict, str, str]:
    prompt = PROMPT1.format(text=text)
    raw = call_llm(prompt, model)
    parsed = parse_json(raw, prompt, model)
    return parsed, prompt, raw


def stage2_reason(brief: dict, model: str) -> tuple[dict, str, str]:
    prompt = PROMPT2.format(brief=json.dumps(brief, indent=2))
    raw = call_llm(prompt, model)
    parsed = parse_json(raw, prompt, model)
    return parsed, prompt, raw


def stage3_produce(brief: dict, decision: dict, model: str) -> tuple[str, str]:
    prompt = PROMPT3.format(
        brief=json.dumps(brief, indent=2),
        decision=json.dumps(decision, indent=2),
    )
    ticket = call_llm(prompt, model)
    return ticket, prompt


def stage4_critique(ticket: str, model: str) -> tuple[dict, str, str]:
    prompt = PROMPT4.format(ticket=ticket)
    raw = call_llm(prompt, model)
    parsed = parse_json(raw, prompt, model)
    return parsed, prompt, raw


# ---------------------------------------------------------------------------
# Main runner — returns a structured dict for the Flask route
# ---------------------------------------------------------------------------

def run_pipeline(text: str, model: str) -> dict:
    result = {"model": model, "stages": [], "error": None}
    t0 = time.time()

    try:
        # Stage 1
        s1_start = time.time()
        brief, p1, r1 = stage1_understand(text, model)
        result["stages"].append({
            "number": 1,
            "name": "UNDERSTAND",
            "technique": "Role + Structured Output",
            "prompt": p1,
            "raw_response": r1,
            "parsed": brief,
            "elapsed": round(time.time() - s1_start, 2),
        })

        # Stage 2
        s2_start = time.time()
        decision, p2, r2 = stage2_reason(brief, model)
        result["stages"].append({
            "number": 2,
            "name": "REASON",
            "technique": "Chain of Thought",
            "prompt": p2,
            "raw_response": r2,
            "parsed": decision,
            "elapsed": round(time.time() - s2_start, 2),
        })

        # Stage 3
        s3_start = time.time()
        ticket, p3 = stage3_produce(brief, decision, model)
        result["stages"].append({
            "number": 3,
            "name": "PRODUCE",
            "technique": "Goal Oriented + Constraints",
            "prompt": p3,
            "raw_response": ticket,
            "parsed": None,
            "elapsed": round(time.time() - s3_start, 2),
        })

        # Stage 4
        s4_start = time.time()
        critique, p4, r4 = stage4_critique(ticket, model)
        final_ticket = ticket
        if not critique.get("passed") and critique.get("revised_ticket"):
            final_ticket = critique["revised_ticket"]
        result["stages"].append({
            "number": 4,
            "name": "CRITIQUE",
            "technique": "Self Check",
            "prompt": p4,
            "raw_response": r4,
            "parsed": critique,
            "elapsed": round(time.time() - s4_start, 2),
            "revised_ticket": critique.get("revised_ticket"),
        })

        result["final_ticket"] = final_ticket
        result["total_elapsed"] = round(time.time() - t0, 2)

    except Exception as exc:
        result["error"] = str(exc)
        result["total_elapsed"] = round(time.time() - t0, 2)

    return result
