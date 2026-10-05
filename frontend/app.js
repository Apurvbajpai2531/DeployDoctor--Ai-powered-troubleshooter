"use strict";

/* ============================================================
   DeployDoctor frontend
   Security rule: untrusted text (logs, AI output) is only ever
   inserted with textContent / text nodes, never innerHTML.
   ============================================================ */

// Keep these in sync with MAX_LOG_CHARS / MAX_UPLOAD_BYTES in .env
const MAX_LOG_CHARS = 50000;
const MAX_UPLOAD_BYTES = 1048576;
const ALLOWED_EXTENSIONS = [".log", ".txt", ".out"];
const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

const $ = (id) => document.getElementById(id);

/* ---------- DOM helper (safe by construction) ---------- */
function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null) continue;
    if (key === "className") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child); // strings become text nodes
  }
  return node;
}

function formatTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

/* ---------- Clipboard (works on http too) ---------- */
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_) {
    /* fall through to the legacy method */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.cssText = "position:fixed;opacity:0;top:0;left:0;";
  document.body.append(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (_) {
    ok = false;
  }
  ta.remove();
  return ok;
}

function copyButton(getText) {
  const btn = el("button", { type: "button", className: "btn btn-secondary", text: "Copy" });
  btn.addEventListener("click", async () => {
    const ok = await copyText(getText());
    btn.textContent = ok ? "Copied" : "Copy failed";
    setTimeout(() => { btn.textContent = "Copy"; }, 1500);
  });
  return btn;
}

/* ---------- Panels: empty / loading / error / result ---------- */
const PANELS = ["panel-empty", "panel-loading", "panel-error", "result"];

function showPanel(id) {
  for (const p of PANELS) $(p).hidden = p !== id;
}

function showError(message) {
  $("error-message").textContent = message;
  showPanel("panel-error");
}

/* ---------- Result rendering ---------- */
function severityBadge(severity, small = false) {
  const s = SEVERITIES.includes(severity) ? severity : "MEDIUM";
  return el("span", { className: `badge sev-${s.toLowerCase()}${small ? " small" : ""}`, text: s });
}

function confidenceMeter(confidence) {
  const pct = Math.max(0, Math.min(100, Math.round((Number(confidence) || 0) * 100)));
  const level = pct >= 80 ? "high" : pct >= 50 ? "mid" : "low";
  const fill = el("span", { className: "meter-fill" });
  fill.style.width = `${pct}%`;
  return el("div", { className: `confidence conf-${level}` }, [
    el("span", { className: "meta-label", text: "Confidence" }),
    el("div", {
      className: "meter", role: "meter", "aria-label": "Confidence",
      "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(pct),
    }, [fill]),
    el("span", { className: "confidence-value", text: `${pct}%` }),
  ]);
}

function metaItem(label, value) {
  return el("div", {}, [
    el("span", { className: "meta-label", text: label }),
    el("span", { className: "meta-value", text: value }),
  ]);
}

function stepCard(num, title, hint, body, extraClass = "") {
  return el("article", { className: `step ${extraClass}`.trim() }, [
    el("header", { className: "step-head" }, [
      el("span", { className: "step-num", text: num }),
      el("h3", { className: "step-title", text: title }),
      el("span", { className: "step-hint", text: hint }),
    ]),
    el("div", { className: "step-body" }, body),
  ]);
}

function listOrEmpty(items, tag, className, emptyText) {
  if (!items || items.length === 0) return el("p", { className: "muted", text: emptyText });
  return el(tag, { className }, items.map((t) => el("li", { text: t })));
}

function renderResult(a) {
  const root = $("result");
  root.replaceChildren();

  const header = el("section", { className: "result-top" }, [
    el("div", { className: "result-top-row" }, [severityBadge(a.severity), confidenceMeter(a.confidence)]),
    el("div", { className: "result-meta" }, [
      metaItem("Affected component", a.affected_component),
      metaItem("Category", a.category),
      metaItem("Analyzed", formatTime(a.created_at)),
      a.ai_model ? metaItem("Model", a.ai_model) : null,
    ]),
  ]);

  const degraded = a.degraded
    ? el("div", { className: "banner banner-warn", role: "status",
        text: "The AI answer could not be validated, so this is a low-confidence fallback. It is not a diagnosis. Try again with a shorter, more focused log." })
    : null;

  const evidence = !a.evidence || a.evidence.length === 0
    ? el("p", { className: "muted", text: "No verifiable evidence lines were found in the log." })
    : a.evidence.map((line) => el("pre", { className: "evidence-line" }, [el("code", { text: line })]));

  const commands = a.commands && a.commands.length > 0
    ? [
        el("span", { className: "sub-label", text: "Commands" }),
        el("p", { className: "safety-note", text: "Recommendations only. Review each command before running it. DeployDoctor never executes anything." }),
        ...a.commands.map((cmd) =>
          el("div", { className: "cmd" }, [
            el("pre", { className: "code-block" }, [el("code", { text: cmd })]),
            copyButton(() => cmd),
          ])),
      ]
    : [];

  root.append(
    header,
    degraded,
    stepCard("01", "Symptom", "What is failing", el("p", { text: a.summary })),
    stepCard("02", "Root cause", "Why it is failing", el("p", { text: a.root_cause })),
    stepCard("03", "Evidence", "Lines from your log that support the diagnosis", evidence),
    stepCard("04", "Fix", "What to do about it", [
      listOrEmpty(a.recommended_fix, "ol", "steps", "No fix steps were returned."),
      ...commands,
    ]),
    stepCard("05", "Prevention", "How to stop it happening again",
      listOrEmpty(a.prevention, "ul", "bullets", "No prevention advice was returned.")),
    a.devops_insight
      ? stepCard("★", "DevOps Insight", "The bigger picture", el("p", { text: a.devops_insight }), "step-insight")
      : null,
  );

  showPanel("result");
  root.scrollIntoView({ behavior: "smooth", block: "start" });
  root.focus({ preventScroll: true });
}

/* ---------- History rendering ---------- */
function renderHistory(items, handlers = {}) {
  const list = $("history-list");
  list.replaceChildren();
  const has = items.length > 0;
  $("history-empty").hidden = has;
  list.hidden = !has;
  $("history-count").textContent = has ? `${items.length} saved` : "";

  for (const item of items) {
    const confidence = `${Math.round((Number(item.confidence) || 0) * 100)}%`;
    const open = el("button", {
      type: "button", className: "history-open",
      "aria-label": `Open analysis from ${formatTime(item.created_at)}`,
      onclick: () => handlers.onOpen && handlers.onOpen(item.id),
    }, [
      severityBadge(item.severity, true),
      el("span", { className: "history-main" }, [
        el("span", { className: "history-summary", text: item.summary }),
        el("span", { className: "history-meta", text: `${item.category} · ${confidence} · ${formatTime(item.created_at)}` }),
      ]),
    ]);

    const del = handlers.onDelete
      ? el("button", {
          type: "button", className: "history-delete", text: "✕",
          "aria-label": `Delete analysis from ${formatTime(item.created_at)}`,
          onclick: () => handlers.onDelete(item.id),
        })
      : null;

    list.append(el("li", { className: "history-item" }, [open, del]));
  }
}

/* ---------- Input handling ---------- */
function setMessage(text, kind = "error") {
  const box = $("form-message");
  box.textContent = text;
  box.className = `form-message ${kind}`;
  box.hidden = !text;
}

function updateCounter() {
  const len = $("log-input").value.length;
  const counter = $("char-count");
  counter.textContent = `${len.toLocaleString()} / ${MAX_LOG_CHARS.toLocaleString()}`;
  counter.classList.toggle("over", len > MAX_LOG_CHARS);
}

function validateInput() {
  const text = $("log-input").value.trim();
  if (!text) return "Paste a log or upload a file first.";
  if (text.length > MAX_LOG_CHARS) {
    return `This log has ${text.length.toLocaleString()} characters; the limit is ${MAX_LOG_CHARS.toLocaleString()}. Paste the section around the first error instead.`;
  }
  return null;
}

async function loadFile(file) {
  const name = file.name || "";
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".")).toLowerCase() : "";
  if (!ALLOWED_EXTENSIONS.includes(ext)) return setMessage("Only .log, .txt and .out files are accepted.");
  if (file.size > MAX_UPLOAD_BYTES) return setMessage("That file is larger than the 1 MB limit.");
  if (file.size === 0) return setMessage("That file is empty.");

  const text = (await file.text()).trim();
  if (text.includes("\u0000")) return setMessage("Binary files are not accepted.");
  if (!text) return setMessage("That file is empty.");
  if (text.length > MAX_LOG_CHARS) {
    return setMessage(`That file has ${text.length.toLocaleString()} characters; the limit is ${MAX_LOG_CHARS.toLocaleString()}. Trim it to the section around the first error.`);
  }

  $("log-input").value = text;
  updateCounter();
  setMessage(`Loaded ${name}.`, "info");
}

// PHASE 10 replaces this with the real call to POST /api/analyze.
function onAnalyzeClick() {
  const problem = validateInput();
  if (problem) return setMessage(problem, "error");
  setMessage("Input looks valid. The connection to the analysis API is added in Phase 10.", "info");
}

/* ---------- Preview mode (?preview=...) for checking every UI state ---------- */
const MOCK_RESULT = {
  id: 1,
  category: "Kubernetes",
  severity: "HIGH",
  confidence: 0.94,
  created_at: new Date().toISOString(),
  ai_model: "openai/gpt-oss-120b",
  degraded: false,
  affected_component: "api pod (Kubernetes, namespace prod)",
  summary: "The api pod keeps crashing and Kubernetes is restarting it in a loop (CrashLoopBackOff).",
  root_cause: "The application crashes on startup because the DATABASE_URL environment variable is not set in the container. Python raises KeyError: 'DATABASE_URL' and exits with code 1.",
  evidence: [
    "Warning  BackOff  40s (x9 over 3m)  kubelet  Back-off restarting failed container api",
    "KeyError: 'DATABASE_URL'",
    "Exit Code: 1",
  ],
  recommended_fix: [
    "Confirm the variable is missing from the running pod.",
    "Add DATABASE_URL to the Deployment from a Secret.",
    "Re-apply the manifest and watch the rollout.",
  ],
  commands: [
    "kubectl describe pod api-7d9f8c6b5-x2k4p -n prod",
    "kubectl create secret generic api-db --from-literal=DATABASE_URL=<YOUR_DATABASE_URL> -n prod",
    "kubectl rollout status deployment/api -n prod",
  ],
  prevention: [
    "Validate required environment variables at startup with a clear error message.",
    "Keep configuration in Secrets or ConfigMaps managed in version control.",
    "Add a readiness probe so broken pods never receive traffic.",
  ],
  devops_insight: "CrashLoopBackOff is a symptom, not a cause: Kubernetes is only reporting that the process keeps dying. The real answer is almost always in the previous container's logs. Failing fast on missing configuration makes these crashes obvious in seconds.",
};

const MOCK_HISTORY = [
  { id: 3, category: "Kubernetes", severity: "HIGH", confidence: 0.94, created_at: new Date().toISOString(), summary: "The api pod keeps crashing and Kubernetes is restarting it in a loop." },
  { id: 2, category: "Database", severity: "CRITICAL", confidence: 0.88, created_at: new Date(Date.now() - 3600e3).toISOString(), summary: "PostgreSQL refuses connections: password authentication failed for user deploy." },
  { id: 1, category: "Docker", severity: "LOW", confidence: 0.52, created_at: new Date(Date.now() - 86400e3).toISOString(), summary: "Image build warns about a deprecated base image tag but completes." },
];

function runPreview(mode) {
  if (mode === "loading") return showPanel("panel-loading");
  if (mode === "error") return showError("The AI service took too long to respond. Please try again.");
  if (mode === "degraded") {
    return renderResult({
      ...MOCK_RESULT, degraded: true, severity: "MEDIUM", confidence: 0, ai_model: "fallback",
      affected_component: "Unknown", evidence: [], commands: [], prevention: [], devops_insight: null,
      summary: "Automatic analysis could not be completed for this log.",
      root_cause: "The AI service returned an answer that could not be validated, so no diagnosis is available.",
      recommended_fix: ["Run the analysis again.", "Paste a shorter excerpt that includes the first error."],
    });
  }
  if (mode === "xss") {
    const payload = `<img src=x onerror="alert('XSS')"><script>alert('XSS')<\/script>`;
    return renderResult({
      ...MOCK_RESULT, summary: payload, root_cause: payload, affected_component: payload,
      evidence: [payload], recommended_fix: [payload], commands: [payload], prevention: [payload], devops_insight: payload,
    });
  }
  if (mode === "history") {
    renderHistory(MOCK_HISTORY, {
      onOpen: () => renderResult(MOCK_RESULT),
      onDelete: (id) => renderHistory(MOCK_HISTORY.filter((h) => h.id !== id)),
    });
    return;
  }
  if (mode === "result") return renderResult(MOCK_RESULT);
}

/* ---------- Init ---------- */
function init() {
  const input = $("log-input");

  input.addEventListener("input", () => { updateCounter(); setMessage(""); });
  input.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") onAnalyzeClick();
  });

  $("clear-btn").addEventListener("click", () => {
    input.value = "";
    updateCounter();
    setMessage("");
    input.focus();
  });

  $("upload-btn").addEventListener("click", () => $("file-input").click());
  $("file-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = ""; // allow re-selecting the same file
    if (file) await loadFile(file);
  });

  $("analyze-btn").addEventListener("click", onAnalyzeClick);
  $("error-retry").addEventListener("click", () => {
    showPanel("panel-empty");
    input.focus();
  });

  updateCounter();
  showPanel("panel-empty");

  const preview = new URLSearchParams(window.location.search).get("preview");
  if (preview) runPreview(preview);
}

document.addEventListener("DOMContentLoaded", init);
