"""
app.py — Flask entry point for the Prompt Pipeline web app.
"""

import os
from flask import Flask, render_template, request, jsonify
from pipeline import run_pipeline

app = Flask(__name__)

MODELS = [
    "openai/gpt-4o-mini",
    "openai/gpt-4.1-mini",
    "openai/gpt-4.1",
    "anthropic/claude-3.5-sonnet",
    "google/gemini-2.5-flash",
]

SAMPLE_INPUTS = {
    "normal": (
        "Title: App crashes when uploading files larger than 50 MB\n\n"
        "Steps:\n"
        "1. Log in as any user.\n"
        "2. Go to Settings > Profile.\n"
        "3. Click 'Upload Avatar' and select a file > 50 MB.\n"
        "4. Click Save.\n\n"
        "Expected: Friendly size-limit error message.\n"
        "Actual: Page freezes for ~10 s then shows a blank white screen.\n"
        "Console:\n"
        "  Uncaught TypeError: Cannot read properties of undefined (reading 'url')\n"
        "      at ProfileUpload.handleResponse (profile.js:142)\n"
        "      at XMLHttpRequest.onload (profile.js:98)\n\n"
        "Browser: Chrome 124 / Windows 11\n"
        "Backend: Node 20 / Express 5, multer 1.4.5 / S3"
    ),
    "tricky": (
        "login broken after last deploy. users cant sign in, says invalid token "
        "but tokens look fine. started around 14:00 UTC today. affects all users. very urgent."
    ),
    "broken": "asdf jkl; qwerty uiop zxcvbnm 1234 !!!",
}


@app.route("/")
def index():
    return render_template("index.html", models=MODELS, samples=SAMPLE_INPUTS)


@app.route("/run", methods=["POST"])
def run():
    data = request.get_json()
    text = (data.get("text") or "").strip()
    model = data.get("model") or MODELS[0]

    if not text:
        return jsonify({"error": "Bug report text is required."}), 400
    if model not in MODELS:
        return jsonify({"error": "Invalid model selected."}), 400
    if not os.environ.get("OPENROUTER_API_KEY"):
        return jsonify({"error": "OPENROUTER_API_KEY environment variable is not set."}), 500

    result = run_pipeline(text, model)
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
