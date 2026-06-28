/* script.js — Prompt Pipeline UI logic */

const runBtn    = document.getElementById("run-btn");
const bugInput  = document.getElementById("bug-input");
const modelSel  = document.getElementById("model-select");
const outputSec = document.getElementById("output-section");
const resultsEl = document.getElementById("results");
const progressBar   = document.getElementById("progress-bar");
const progressLabel = document.getElementById("progress-label");

// ── Sample buttons ────────────────────────────────────────────
document.querySelectorAll(".btn-sample").forEach(btn => {
  btn.addEventListener("click", () => {
    bugInput.value = SAMPLES[btn.dataset.key];
    bugInput.focus();
  });
});

// ── JSON syntax highlighter ───────────────────────────────────
function highlightJSON(obj) {
  const raw = JSON.stringify(obj, null, 2);
  return raw.replace(
    /("(\\u[\dA-Fa-f]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(\.\d+)?([eE][+-]?\d+)?)/g,
    match => {
      if (/^"/.test(match)) {
        return /:$/.test(match)
          ? `<span class="json-key">${match}</span>`
          : `<span class="json-str">${match}</span>`;
      }
      if (/true|false/.test(match)) return `<span class="json-bool">${match}</span>`;
      if (/null/.test(match))        return `<span class="json-null">${match}</span>`;
      return `<span class="json-num">${match}</span>`;
    }
  );
}

function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ── Set progress bar ──────────────────────────────────────────
function setProgress(pct, label) {
  progressBar.style.setProperty("--pct", pct + "%");
  progressLabel.textContent = label;
}

// ── Build a stage card ────────────────────────────────────────
function buildStageCard(stage) {
  const cls = ["s1","s2","s3","s4"][stage.number - 1];
  const colors = ["Stage 1","Stage 2","Stage 3","Stage 4"];

  let bodyHTML = `
    <div class="sub-section">
      <div class="sub-label">Prompt Used</div>
      <pre>${esc(stage.prompt)}</pre>
    </div>
    <div class="sub-section">
      <div class="sub-label">Raw LLM Response</div>
      <pre>${esc(stage.raw_response)}</pre>
    </div>`;

  if (stage.parsed) {
    bodyHTML += `
      <div class="sub-section">
        <div class="sub-label">Parsed JSON</div>
        <pre><code>${highlightJSON(stage.parsed)}</code></pre>
      </div>`;
  }

  // Stage 4 extras: scores + revised ticket
  if (stage.number === 4 && stage.parsed) {
    const c = stage.parsed;
    const passed = c.passed;
    const scores = c.scores || {};
    bodyHTML += `
      <div class="sub-section">
        <div class="sub-label">Quality Scores</div>
        <div class="scores-row">
          <div class="score-pill">Completeness <span>${scores.completeness ?? "—"}</span>/10</div>
          <div class="score-pill">Actionability <span>${scores.actionability ?? "—"}</span>/10</div>
          <div class="score-pill">Clarity <span>${scores.clarity ?? "—"}</span>/10</div>
          <div class="score-pill">Overall <span>${c.overall ?? "—"}</span>/10</div>
        </div>
        <span class="pass-badge ${passed ? "pass" : "fail"}">${passed ? "✓ PASSED" : "✗ FAILED — regenerating"}</span>
        <div class="meta-row">${esc(c.feedback || "")}</div>
      </div>`;

    if (!passed && c.revised_ticket) {
      bodyHTML += `
        <div class="sub-section">
          <div class="sub-label">Revised Ticket (auto-regenerated)</div>
          <div class="ticket-box">${esc(c.revised_ticket)}</div>
        </div>`;
    }
  }

  return `
    <div class="stage-card ${cls}" id="stage-${stage.number}">
      <div class="stage-header" onclick="toggleCard(this)">
        <span class="stage-badge">${colors[stage.number-1]}</span>
        <span class="stage-title">STAGE ${stage.number} — ${esc(stage.name)}</span>
        <span class="stage-technique">${esc(stage.technique)}</span>
        <span class="stage-time">${stage.elapsed}s</span>
        <span class="chevron">▼</span>
      </div>
      <div class="stage-body">${bodyHTML}</div>
    </div>`;
}

// ── Toggle collapse ───────────────────────────────────────────
function toggleCard(header) {
  header.closest(".stage-card").classList.toggle("collapsed");
}

// ── Render full results ───────────────────────────────────────
function renderResults(data, inputText) {
  let html = "";

  // Input block
  html += `
    <div class="stage-card input-card">
      <div class="stage-header" onclick="toggleCard(this)">
        <span class="stage-badge">INPUT</span>
        <span class="stage-title">Bug Report Submitted</span>
        <span class="stage-technique">${esc(data.model)}</span>
        <span class="stage-time">${data.total_elapsed}s total</span>
        <span class="chevron">▼</span>
      </div>
      <div class="stage-body">
        <pre>${esc(inputText)}</pre>
      </div>
    </div>`;

  if (data.error) {
    html += `<div class="error-box">Pipeline error:\n${esc(data.error)}</div>`;
    resultsEl.innerHTML = html;
    return;
  }

  // Stage cards
  (data.stages || []).forEach(s => { html += buildStageCard(s); });

  // Final result
  html += `
    <div class="final-card">
      <div class="final-header">★ FINAL BUG TICKET</div>
      <div class="final-body">
        <div class="ticket-box">${esc(data.final_ticket || "")}</div>
      </div>
    </div>`;

  resultsEl.innerHTML = html;
}

// ── Run button handler ────────────────────────────────────────
runBtn.addEventListener("click", async () => {
  const text  = bugInput.value.trim();
  const model = modelSel.value;

  if (!text) { bugInput.focus(); return; }

  runBtn.disabled = true;
  outputSec.classList.remove("hidden");
  resultsEl.innerHTML = "";
  setProgress(10, "Sending to pipeline…");

  // Simulate progress during the async call
  const stages = ["Stage 1: Understand…", "Stage 2: Reason…", "Stage 3: Produce…", "Stage 4: Critique…"];
  let tick = 0;
  const interval = setInterval(() => {
    tick = Math.min(tick + 1, stages.length - 1);
    setProgress(10 + tick * 20, stages[tick]);
  }, 8000);

  try {
    const resp = await fetch("/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, model }),
    });
    const data = await resp.json();
    clearInterval(interval);
    setProgress(100, "Done!");
    renderResults(data, text);
    // Scroll to results
    outputSec.scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    clearInterval(interval);
    setProgress(0, "Error");
    resultsEl.innerHTML = `<div class="error-box">Request failed: ${esc(err.message)}</div>`;
  } finally {
    runBtn.disabled = false;
  }
});
