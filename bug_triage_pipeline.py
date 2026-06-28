"""
Bug Report Triage Pipeline
==========================
Stage 1 . UNDERSTAND  (role + structured output)   -- extract structured fields from raw bug report
Stage 2 . REASON      (chain-of-thought)            -- determine root cause, severity, suggested fix
Stage 3 . PRODUCE     (goal-oriented + constraints) -- write a developer-ready triage summary
Stage 4 . CRITIQUE    (self-check / stretch goal)   -- grade Stage 3 output and request redo if weak

Technique labels: role, structured_output, chain_of_thought, goal_oriented
"""

import os, json, re, textwrap

# -- LLM helper --------------------------------------------------------------

import requests

import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "openai/gpt-4o-mini"

def call_llm(prompt: str, model: str = MODEL) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY not found. Please add it to your .env file."
        )

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        },
        timeout=60,
    )

    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()

# -- JSON parsing with one retry ----------------------------------------------

def parse_json(raw: str, prompt_on_fail: str, max_retries: int = 2) -> dict:
    """Extract JSON from model output; re-prompt once on parse failure."""
    for attempt in range(max_retries):
        # pull out the first {...} block
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        candidate = match.group(0) if match else raw
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as err:
            if attempt + 1 == max_retries:
                raise ValueError(f"Could not parse JSON after {max_retries} attempts: {err}\nRaw:\n{raw}")
            repair_prompt = (
                f"{prompt_on_fail}\n\n"
                f"Your previous response could not be parsed as JSON.\n"
                f"Error: {err}\n"
                f"Bad output:\n{raw}\n\n"
                "Return ONLY valid JSON, no prose, no markdown fences."
            )
            raw = call_llm(repair_prompt)


# -- Display helper -----------------------------------------------------------

def show(stage: str, technique: str, data):
    bar = "-" * 60
    print(f"\n{bar}")
    print(f"  {stage}  [{technique}]")
    print(bar)
    if isinstance(data, dict):
        print(json.dumps(data, indent=2))
    else:
        print(textwrap.fill(str(data), width=80))


# -- Prompts ------------------------------------------------------------------

PROMPT1 = """You are a senior QA engineer specialising in bug triage.
Your job is to read a raw bug report and extract every relevant fact.

Bug report:
\"\"\"
{text}
\"\"\"

Instructions:
- If any field cannot be determined from the text, use null.
- If the report is in a non-English language, translate field values to English.
- If the report is gibberish or completely empty, set "parse_error" to a short explanation and all other fields to null.
- Return ONLY valid JSON -- no prose, no markdown fences.

Return this exact schema:
{{
  "title": "<one-line summary>",
  "component": "<module or service affected, or null>",
  "environment": "<OS / browser / version, or null>",
  "steps_to_reproduce": ["<step 1>", "..."],
  "expected_behaviour": "<what should happen>",
  "actual_behaviour": "<what actually happens>",
  "error_message": "<exact error or exception text, or null>",
  "stack_trace": "<condensed stack trace, or null>",
  "reporter_sentiment": "frustrated | neutral | calm",
  "parse_error": null
}}"""

PROMPT2 = """You are a principal engineer performing root-cause analysis.
Think step by step before committing to any answer.

Structured bug brief (JSON):
{brief}

Step-by-step reasoning instructions:
1. Identify the most likely root-cause category from: null_pointer | race_condition | config_error | dependency_version | logic_bug | network_timeout | auth_failure | unknown.
2. Assess severity: P0 (system down) | P1 (major feature broken) | P2 (minor degradation) | P3 (cosmetic).
3. Propose ONE concrete fix (code change, config tweak, or investigation step).
4. Assign an owner team from: frontend | backend | infra | data | qa | unknown.
5. Estimate fix effort: trivial (<1 h) | small (1-4 h) | medium (1-2 d) | large (>2 d).

After reasoning, return ONLY valid JSON -- no prose, no markdown fences:
{{
  "reasoning_chain": [
    "Step 1: ...",
    "Step 2: ...",
    "Step 3: ...",
    "Step 4: ...",
    "Step 5: ..."
  ],
  "root_cause_category": "<category>",
  "root_cause_explanation": "<one or two sentences>",
  "severity": "P0|P1|P2|P3",
  "suggested_fix": "<actionable fix>",
  "owner_team": "<team>",
  "fix_effort": "trivial|small|medium|large"
}}"""

PROMPT3 = """You are a technical writer creating a developer-ready triage ticket.

Bug brief (Stage 1):
{brief}

Engineering analysis (Stage 2):
{decision}

Write a triage summary following these constraints:
- Start with a one-line "## [SEVERITY] Title" heading.
- Include sections: Summary, Steps to Reproduce, Root Cause, Suggested Fix, Owner & Effort.
- Total length: 150-250 words.
- Tone: precise, professional, no filler phrases.
- If parse_error is set in the brief, open with a "(!) Incomplete report" warning and note what is missing.
- Return plain text only -- no JSON, no markdown code fences."""

PROMPT4 = """You are a quality reviewer for engineering triage tickets.

Ticket under review:
\"\"\"
{ticket}
\"\"\"

Grade the ticket on these criteria (each 0-10):
1. Completeness -- are all sections present?
2. Actionability -- is the suggested fix concrete?
3. Clarity -- is it easy to read and unambiguous?

Return ONLY valid JSON:
{{
  "scores": {{"completeness": 0, "actionability": 0, "clarity": 0}},
  "overall": 0,
  "passed": true,
  "feedback": "<one sentence if failed, else 'Looks good.'>",
  "revised_ticket": null
}}

Rules:
- overall = average of the three scores (round to 1 decimal).
- passed = true if overall >= 7, else false.
- If passed is false, set revised_ticket to an improved version of the ticket (same format constraints as before)."""


# -- Pipeline stages ----------------------------------------------------------

def stage1_understand(text: str) -> dict:
    prompt = PROMPT1.format(text=text)
    raw = call_llm(prompt)
    return parse_json(raw, prompt)


def stage2_reason(brief: dict) -> dict:
    prompt = PROMPT2.format(brief=json.dumps(brief, indent=2))
    raw = call_llm(prompt)
    return parse_json(raw, prompt)


def stage3_produce(brief: dict, decision: dict) -> str:
    prompt = PROMPT3.format(
        brief=json.dumps(brief, indent=2),
        decision=json.dumps(decision, indent=2),
    )
    return call_llm(prompt)


def stage4_critique(ticket: str) -> dict:
    prompt = PROMPT4.format(ticket=ticket)
    raw = call_llm(prompt)
    return parse_json(raw, prompt)


# -- Runner -------------------------------------------------------------------

def run(label: str, text: str, use_stage4: bool = True) -> str:
    print(f"\n{'=' * 60}")
    print(f"  RUN: {label}")
    print(f"  INPUT:\n{textwrap.indent(textwrap.fill(text, 80), '  ')}")
    print(f"{'=' * 60}")

    brief    = stage1_understand(text)
    show("STAGE 1 . UNDERSTAND", "role + structured_output", brief)

    decision = stage2_reason(brief)
    show("STAGE 2 . REASON", "chain_of_thought", decision)

    ticket   = stage3_produce(brief, decision)
    show("STAGE 3 . PRODUCE", "goal_oriented + constraints", ticket)

    if use_stage4:
        critique = stage4_critique(ticket)
        show("STAGE 4 . CRITIQUE", "self_check", critique)
        if not critique.get("passed") and critique.get("revised_ticket"):
            show("STAGE 4 . REVISED TICKET", "self_check", critique["revised_ticket"])
            return critique["revised_ticket"]

    return ticket


# -- Test inputs ---------------------------------------------------------------

INPUTS = {
    "Run 1 -- Normal bug with stack trace": """\
Title: App crashes when uploading files larger than 50 MB

Steps:
1. Log in as any user.
2. Navigate to Settings > Profile.
3. Click "Upload Avatar" and select a file larger than 50 MB.
4. Click Save.

Expected: File is rejected with a friendly size-limit message.
Actual: The page freezes for ~10 s then shows a blank white screen.
The browser console shows:
  Uncaught TypeError: Cannot read properties of undefined (reading 'url')
      at ProfileUpload.handleResponse (profile.js:142)
      at XMLHttpRequest.onload (profile.js:98)

Browser: Chrome 124 on Windows 11
Backend: Node 20 / Express 5, S3 upload via multer 1.4.5
""",

    "Run 2 -- Tricky: terse report, no stack trace": """\
login broken after last deploy. users cant sign in, says invalid token but tokens look fine.
started around 14:00 UTC today. affects all users. very urgent.
""",

    "Run 3 -- Bad input (gibberish / missing fields)": """\
asdf jkl; qwerty uiop zxcvbnm 1234 !!!
""",
}

# -- Reflection ----------------------------------------------------------------

REFLECTION = """
+--------------------------------------------------------------+
|  WEAKEST LINK -- REFLECTION                                  |
+--------------------------------------------------------------+
  Stage 2 (REASON) is the weakest link.  Its chain-of-thought
  analysis depends entirely on what Stage 1 extracted; if the
  bug report is terse or ambiguous (as in Run 2), the model
  must guess the root-cause category from very little signal,
  and the suggested fix can be too vague to act on.  You would
  know it's weak when the fix reads as "investigate logs"
  instead of a concrete code change.  On Day 4, feeding Stage
  2 a retrieval step -- pulling similar past bugs and their
  confirmed root causes from a vector store -- would ground the
  reasoning in real precedents.  On Days 6-8 a tool call that
  fetches the relevant git diff or error-log tail would give
  the model hard evidence instead of pattern-matching alone.
+--------------------------------------------------------------+
"""

# -- Entry point ---------------------------------------------------------------

if __name__ == "__main__":
    for label, text in INPUTS.items():
        run(label, text, use_stage4=True)
    print(REFLECTION)
