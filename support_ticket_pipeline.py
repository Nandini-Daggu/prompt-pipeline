````python
"""
SUPPORT TICKET TRIAGE PIPELINE
Part 1 of 2

Contains:
✔ Imports
✔ Configuration
✔ OpenRouter Client
✔ JSON Parsing
✔ Validation
✔ Stage 1
✔ Stage 2
✔ Helper Functions
"""

import json
import os
import re
import urllib.request
import urllib.error
from typing import Dict, Any

# ============================================================
# CONFIGURATION
# ============================================================

MODEL = "openai/gpt-4.1-mini"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    raise RuntimeError(
        "OPENROUTER_API_KEY environment variable is not set."
    )


# ============================================================
# OPENROUTER CLIENT
# ============================================================

class OpenRouterClient:

    def __init__(self,
                 api_key: str,
                 model: str = MODEL):
        self.api_key = api_key
        self.model = model
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    def chat(
        self,
        system: str,
        prompt: str,
        temperature: float = 0.0,
        max_retries: int = 3,
    ) -> str:

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "Support Ticket Pipeline"
        }

        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {
                    "role": "system",
                    "content": system
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        data = json.dumps(payload).encode()

        last_error = None

        for attempt in range(max_retries):

            try:

                req = urllib.request.Request(
                    self.url,
                    data=data,
                    headers=headers,
                    method="POST"
                )

                with urllib.request.urlopen(
                    req,
                    timeout=120
                ) as response:

                    body = json.loads(
                        response.read().decode("utf-8")
                    )

                if "choices" not in body:
                    raise RuntimeError(body)

                return body["choices"][0]["message"]["content"]

            except urllib.error.HTTPError as e:

                error_text = e.read().decode()

                last_error = RuntimeError(error_text)

            except Exception as e:

                last_error = e

        raise last_error


client = OpenRouterClient(
    OPENROUTER_API_KEY
)


# ============================================================
# JSON EXTRACTION
# ============================================================

def extract_json(text: str) -> Dict[str, Any]:

    text = text.strip()

    match = re.search(
        r"```(?:json)?\s*(.*?)```",
        text,
        re.S
    )

    if match:
        text = match.group(1).strip()

    return json.loads(text)


# ============================================================
# JSON VALIDATION
# ============================================================

def validate_json(
    obj: Dict[str, Any],
    required_keys
):

    for key in required_keys:

        if key not in obj:
            obj[key] = None

    return obj


def parse_response(
    raw: str,
    required_keys
):

    obj = extract_json(raw)

    return validate_json(
        obj,
        required_keys
    )


# ============================================================
# STAGE 1
# ============================================================

STAGE1_SYSTEM = """
You are an expert customer support analyst.

Extract information accurately.

Never invent information.

Return ONLY valid JSON.
"""

STAGE1_PROMPT = """
Read the customer message.

Return JSON with:

customer_name
order_id
issue_category
issue_summary
days_waiting
sentiment
language
missing_fields

Categories:
billing
shipping
product_defect
account
other

Customer message:

{text}
"""


def stage1_understand(
    customer_message: str
):

    prompt = STAGE1_PROMPT.format(
        text=customer_message
    )

    raw = client.chat(
        STAGE1_SYSTEM,
        prompt,
        temperature=0
    )

    required = [

        "customer_name",

        "order_id",

        "issue_category",

        "issue_summary",

        "days_waiting",

        "sentiment",

        "language",

        "missing_fields"
    ]

    return parse_response(
        raw,
        required
    )


# ============================================================
# STAGE 2
# ============================================================

STAGE2_SYSTEM = """
You are a support ticket triage manager.

Determine:

Priority

Routing team

Urgency

Return ONLY JSON.
"""

STAGE2_PROMPT = """
Ticket summary:

{summary}

Return JSON:

priority

route_to

summary

urgency_flags
"""


def stage2_reason(
    stage1_output: Dict[str, Any]
):

    prompt = STAGE2_PROMPT.format(
        summary=json.dumps(
            stage1_output,
            indent=2
        )
    )

    raw = client.chat(

        STAGE2_SYSTEM,

        prompt,

        temperature=0
    )

    required = [

        "priority",

        "route_to",

        "summary",

        "urgency_flags"
    ]

    return parse_response(
        raw,
        required
    )


# ============================================================
# PRETTY PRINT
# ============================================================

def show(title, data):

    print("\n" + "=" * 60)

    print(title)

    print("=" * 60)

    print(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        )
    )
````
