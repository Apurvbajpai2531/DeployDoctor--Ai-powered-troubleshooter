"use strict";

/* ============================================================
   DeployDoctor frontend
   Security rule: untrusted text (logs, AI output) is only ever
   inserted with textContent or text nodes. Markup is never built
   from strings, so injected HTML is shown as plain text.
   ============================================================ */

// Keep these in sync with MAX_LOG_CHARS / MAX_UPLOAD_BYTES in .env
const MAX_LOG_CHARS = 50000;
const MAX_UPLOAD_BYTES = 1048576;
const ALLOWED_EXTENSIONS = [".log", ".txt", ".out"];
const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

const SEVERITY_INFO = {
  LOW: "Minor issue. The service still works.",
  MEDIUM: "Degraded. A workaround is likely.",
  HIGH: "A service or deployment is failing.",
  CRITICAL: "Outage, data-loss risk, or security exposure.",
};

const ANALYZE_TIMEOUT_MS = 90000;
const UPLOAD_TIMEOUT_MS = 30000;
const HISTORY_PAGE = 20;
const HISTORY_MAX = 100; // the API caps a page at 100
const HISTORY_EMPTY_TEXT = "Your previous analyses will appear here.";
const SESSION_KEY = "deploydoctor_session_id";
const SESSION_RE = /^[A-Za-z0-9-]{16,64}$/;

// Mutable state
let busy = false;
let currentAnalysisId = null; // id of the analysis shown in the result panel
let historyItems = [];
let historyTotal = 0;
let loadingTimer = null;
let memorySessionId = null;

const $ = (id) => document.getElementById(id);

/* ---------- DOM helpers (safe by construction) ---------- */
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

const SVG_NS = "http://www.w3.org/2000/svg";
const ICON_PATHS = {
  copy: "M8 8h11v12H8z M5 16H4V4h11v1",
  check: "M5 12l5 5 9-10",
  trash: "M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13 M10 11v6 M14 11v6",
  download: "M12 4v12 M7 11l5 5 5-5 M4 20h16",
};

function icon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  const attrs = {
    viewBox: "0 0 24 24", width: "16", height: "16", fill: "none", stroke: "currentColor",
    "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round",
    "aria-hidden": "true", class: "icon",
  };
  for (const [k, v] of Object.entries(attrs)) svg.setAttribute(k, v);
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", ICON_PATHS[name]);
  svg.append(path);
  return svg;
}

function scrollBehavior() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
}

function formatTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function timeAgo(iso) {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const seconds = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} d ago`;
  return new Date(t).toLocaleDateString([], { dateStyle: "medium" });
}

/* ---------- Clipboard (works on plain http too) ---------- */
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
  Object.assign(ta.style, { position: "fixed", opacity: "0", top: "0", left: "0" });
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

function copyButton(getText, label = "Copy", className = "btn btn-secondary btn-small") {
  const btn = el("button", { type: "button", className }, [icon("copy"), label]);
  btn.addEventListener("click", async () => {
    const ok = await copyText(getText());
    btn.replaceChildren(icon(ok ? "check" : "copy"), ok ? "Copied" : "Copy failed");
    setTimeout(() => btn.replaceChildren(icon("copy"), label), 1600);
  });
  return btn;
}

/* ---------- Toasts and confirm dialog ---------- */
function toast(message, kind = "info") {
  const node = el("div", {
    className: `toast toast-${kind}`,
    role: kind === "error" ? "alert" : "status",
    text: message,
  });
  $("toast-region").append(node);
  setTimeout(() => node.remove(), kind === "error" ? 6000 : 3000);
}

function confirmDialog({ title, message, confirmLabel = "Confirm" }) {
  const dialog = $("confirm-dialog");
  if (typeof dialog.showModal !== "function") return Promise.resolve(window.confirm(message));

  $("confirm-title").textContent = title;
  $("confirm-message").textContent = message;
  $("confirm-ok").textContent = confirmLabel;

  return new Promise((resolve) => {
    const finish = (result) => {
      $("confirm-ok").removeEventListener("click", onOk);
      $("confirm-cancel").removeEventListener("click", onCancel);
      dialog.removeEventListener("close", onClose);
      if (dialog.open) dialog.close();
      resolve(result);
    };
    const onOk = () => finish(true);
    const onCancel = () => finish(false);
    const onClose = () => finish(false); // Escape key
    $("confirm-ok").addEventListener("click", onOk);
    $("confirm-cancel").addEventListener("click", onCancel);
    dialog.addEventListener("close", onClose);
    dialog.showModal();
    $("confirm-cancel").focus();
  });
}

/* ---------- PDF report ---------- */
async function downloadPdf(a, btn) {
  if (a.preview) return toast("PDF download is not available for preview data.", "error");

  btn.disabled = true;
  btn.replaceChildren(icon("download"), "Preparing PDF…");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);
  try {
    const res = await fetch(`/api/analyses/${a.id}/pdf`, {
      headers: { "X-Session-ID": getSessionId() },
      signal: controller.signal,
    });
    if (!res.ok) {
      let body = null;
      try {
        body = await res.json();
      } catch (_) {
        /* not JSON: use the generic message */
      }
      throw new ApiError(errorMessageFrom(res.status, body), res.status);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = el("a", { href: url, download: `deploydoctor-diagnosis-${a.id}.pdf` });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    toast("PDF downloaded");
  } catch (err) {
    let message = "Cannot reach the server. Check your connection and try again.";
    if (err instanceof ApiError) message = err.message;
    else if (err.name === "AbortError") message = "The request timed out. Please try again.";
    toast(`Could not create the PDF. ${message}`, "error");
  } finally {
    clearTimeout(timer);
    btn.disabled = false;
    btn.replaceChildren(icon("download"), "Download PDF");
  }
}

function pdfButton(a) {
  const btn = el("button", { type: "button", className: "btn btn-secondary btn-small" }, [
    icon("download"),
    "Download PDF",
  ]);
  btn.addEventListener("click", () => downloadPdf(a, btn));
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

function startLoadingTimer() {
  const started = Date.now();
  $("loading-elapsed").textContent = "0s";
  clearInterval(loadingTimer);
  loadingTimer = setInterval(() => {
    $("loading-elapsed").textContent = `${Math.floor((Date.now() - started) / 1000)}s`;
  }, 1000);
}

function stopLoadingTimer() {
  clearInterval(loadingTimer);
  loadingTimer = null;
}

/* ---------- Result rendering ---------- */
function normalizedSeverity(severity) {
  return SEVERITIES.includes(severity) ? severity : "MEDIUM";
}

function severityBadge(severity, small = false) {
  const s = normalizedSeverity(severity);
  return el("span", { className: `badge sev-${s.toLowerCase()}${small ? " small" : ""}`, text: s });
}

function confidenceRing(confidence) {
  const pct = Math.max(0, Math.min(100, Math.round((Number(confidence) || 0) * 100)));
  const level = pct >= 80 ? "high" : pct >= 50 ? "mid" : "low";
  const radius = 26;
  const circumference = 2 * Math.PI * radius;

  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 64 64");
  svg.setAttribute("class", "ring");
  svg.setAttribute("aria-hidden", "true");

  const ringCircle = (cls, dash) => {
    const c = document.createElementNS(SVG_NS, "circle");
    c.setAttribute("cx", "32");
    c.setAttribute("cy", "32");
    c.setAttribute("r", String(radius));
    c.setAttribute("fill", "none");
    c.setAttribute("stroke-width", "6");
    c.setAttribute("class", cls);
    if (dash) {
      c.setAttribute("stroke-dasharray", dash);
      c.setAttribute("stroke-linecap", "round");
      c.setAttribute("transform", "rotate(-90 32 32)");
    }
    return c;
  };
  svg.append(ringCircle("ring-track"), ringCircle("ring-value", `${(pct / 100) * circumference} ${circumference}`));

  return el("div", {
    className: `confidence conf-${level}`, role: "meter", "aria-label": "Confidence",
    "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(pct),
  }, [
    svg,
    el("div", { className: "confidence-text" }, [
      el("span", { className: "confidence-value", text: `${pct}%` }),
      el("span", { className: "confidence-label", text: "confidence" }),
    ]),
  ]);
}

function metaItem(label, value) {
  return el("div", {}, [el("dt", { text: label }), el("dd", { text: value })]);
}

function stage(number, title, hint, body) {
  return el("li", { className: "stage" }, [
    el("div", { className: "stage-rail", "aria-hidden": "true" }, [
      el("span", { className: "stage-node", text: String(number) }),
    ]),
    el("div", { className: "stage-content" }, [
      el("header", { className: "stage-head" }, [
        el("h3", { text: title }),
        el("span", { className: "stage-hint", text: hint }),
      ]),
      el("div", { className: "stage-body" }, body),
    ]),
  ]);
}

function listOrEmpty(items, tag, className, emptyText) {
  if (!items || items.length === 0) return el("p", { className: "muted", text: emptyText });
  return el(tag, { className }, items.map((t) => el("li", { text: t })));
}

function toMarkdown(a) {
  const F = "\x60\x60\x60"; // a markdown code fence
  const pct = Math.round((Number(a.confidence) || 0) * 100);
  const numbered = (items) => items.map((t, i) => `${i + 1}. ${t}`).join("\n");
  const bullets = (items) => items.map((t) => `- ${t}`).join("\n");

  const out = [
    "# DeployDoctor diagnosis", "",
    `- Severity: ${a.severity}`,
    `- Confidence: ${pct}%`,
    `- Affected component: ${a.affected_component}`,
    `- Category: ${a.category}`,
    `- Analyzed: ${formatTime(a.created_at)}`, "",
    "## Symptom", a.summary, "",
    "## Root cause", a.root_cause, "",
  ];
  if (a.evidence && a.evidence.length) out.push("## Evidence", F, ...a.evidence, F, "");
  out.push("## Fix", numbered(a.recommended_fix || []));
  if (a.commands && a.commands.length) {
    out.push("", "Commands (review before running):", "", F, ...a.commands, F);
  }
  out.push("", "## Prevention", bullets(a.prevention || []));
  if (a.devops_insight) out.push("", "## DevOps insight", a.devops_insight);
  return out.join("\n") + "\n";
}

function renderResult(a) {
  const root = $("result");
  root.replaceChildren();
  const sev = normalizedSeverity(a.severity);

  const vitals = el("section", { className: `vitals vitals-${sev.toLowerCase()}`, "aria-label": "Diagnosis summary" }, [
    el("div", {}, [
      severityBadge(sev),
      el("p", { className: "vitals-text", text: SEVERITY_INFO[sev] }),
    ]),
    confidenceRing(a.confidence),
    el("dl", { className: "vitals-meta" }, [
      metaItem("Affected component", a.affected_component),
      metaItem("Category", a.category),
      metaItem("Analyzed", formatTime(a.created_at)),
      a.ai_model ? metaItem("Model", a.ai_model) : null,
    ]),
    el("div", { className: "vitals-actions" }, [
      pdfButton(a),
      copyButton(() => toMarkdown(a), "Copy report"),
    ]),
  ]);

  const degraded = a.degraded
    ? el("div", {
        className: "banner banner-warn", role: "status",
        text: "The AI answer could not be validated, so this is a low-confidence fallback. It is not a diagnosis. Try again with a shorter, more focused log.",
      })
    : null;

  const redacted = a.redactions > 0
    ? el("div", {
        className: "banner banner-info", role: "status",
        text: `${a.redactions} sensitive value${a.redactions === 1 ? "" : "s"} (keys, tokens, or passwords) ${a.redactions === 1 ? "was" : "were"} masked before analysis and saving.`,
      })
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

  const record = el("ol", { className: "record" }, [
    stage(1, "Symptom", "What is failing", el("p", { text: a.summary })),
    stage(2, "Root cause", "Why it is failing", el("p", { text: a.root_cause })),
    stage(3, "Evidence", "Lines from your log that support the diagnosis", evidence),
    stage(4, "Fix", "What to do about it", [
      listOrEmpty(a.recommended_fix, "ol", "steps", "No fix steps were returned."),
      ...commands,
    ]),
    stage(5, "Prevention", "How to stop it happening again",
      listOrEmpty(a.prevention, "ul", "bullets", "No prevention advice was returned.")),
  ]);

  const insight = a.devops_insight
    ? el("aside", { className: "insight" }, [
        el("h3", { text: "DevOps Insight" }),
        el("p", { text: a.devops_insight }),
      ])
    : null;

  root.append(vitals, degraded, redacted, record, insight);
  showPanel("result");
  root.scrollIntoView({ behavior: scrollBehavior(), block: "start" });
  root.focus({ preventScroll: true });
}

/* ---------- History rendering ---------- */
function renderHistory(items, handlers = {}) {
  const list = $("history-list");
  list.replaceChildren();
  const has = items.length > 0;
  $("history-empty").hidden = has;
  list.hidden = !has;
  const total = handlers.total ?? items.length;
  $("history-count").textContent = has
    ? (total > items.length ? `Showing ${items.length} of ${total}` : `${total} saved`)
    : "";

  for (const item of items) {
    const confidence = `${Math.round((Number(item.confidence) || 0) * 100)}%`;
    const open = el("button", {
      type: "button", className: "history-open",
      "aria-label": `Open analysis from ${formatTime(item.created_at)}`,
      "aria-current": item.id === currentAnalysisId ? "true" : null,
      onclick: () => handlers.onOpen && handlers.onOpen(item.id),
    }, [
      el("span", { className: "history-top" }, [
        severityBadge(item.severity, true),
        el("span", { className: "history-time", title: formatTime(item.created_at), text: timeAgo(item.created_at) }),
      ]),
      el("span", { className: "history-summary", text: item.summary }),
      el("span", { className: "history-meta" }, [
        el("span", { className: "tag", text: item.category }),
        el("span", { text: `${confidence} confidence` }),
      ]),
    ]);

    const del = handlers.onDelete
      ? el("button", {
          type: "button", className: "history-delete",
          "aria-label": `Delete analysis from ${formatTime(item.created_at)}`,
          onclick: () => handlers.onDelete(item.id),
        }, [icon("trash")])
      : null;

    list.append(el("li", { className: "history-item" }, [open, del]));
  }
}

/* ---------- Input handling ---------- */
function setMessage(text, kind = "error") {
  const box = $("form-message");
  box.textContent = text;
  box.className = `form-message ${kind}`;
  box.setAttribute("role", kind === "error" ? "alert" : "status");
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

/* ---------- Session ID (anonymous, per browser) ---------- */
function generateId() {
  if (window.crypto && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // randomUUID is unavailable on plain http (non-localhost): build a v4 UUID by hand
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

function getSessionId() {
  try {
    const stored = localStorage.getItem(SESSION_KEY);
    if (stored && SESSION_RE.test(stored)) return stored;
    const fresh = generateId();
    localStorage.setItem(SESSION_KEY, fresh);
    return fresh;
  } catch (_) {
    // storage blocked: keep an in-memory ID for this tab
    if (!memorySessionId) memorySessionId = generateId();
    return memorySessionId;
  }
}

/* ---------- API layer ---------- */
class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.status = status;
  }
}

function errorMessageFrom(status, body) {
  const detail = body && body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return String(detail[0].msg || "Invalid input").replace(/^Value error, /, "");
  }
  if (status === 413) return "That input is too large.";
  if (status === 429) return "Too many requests. Please wait a moment and try again.";
  if (status >= 500) return "The server had a problem. Please try again.";
  return `Request failed (${status}).`;
}

async function apiFetch(path, options = {}, timeoutMs = ANALYZE_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: { "X-Session-ID": getSessionId(), ...(options.headers || {}) },
      signal: controller.signal,
    });
  } catch (err) {
    if (err.name === "AbortError") throw new ApiError("The request timed out. Please try again.");
    throw new ApiError("Cannot reach the server. Check your connection and try again.");
  } finally {
    clearTimeout(timer);
  }

  if (response.status === 204) return null;

  let body = null;
  try {
    body = await response.json();
  } catch (_) {
    /* non-JSON error page: fall back to a generic message */
  }
  if (!response.ok) throw new ApiError(errorMessageFrom(response.status, body), response.status);
  return body;
}

/* ---------- API status in the header ---------- */
function setApiStatus(kind, text) {
  const badge = $("api-status");
  badge.className = `status status-${kind}`;
  badge.textContent = text;
}

async function checkApiStatus() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch("/health", { cache: "no-store", signal: controller.signal });
    const body = await res.json().catch(() => null);
    if (res.ok && body && body.status === "ok") setApiStatus("ok", "API online");
    else if (body && body.database === "unavailable") setApiStatus("warn", "Database unavailable");
    else setApiStatus("warn", "API degraded");
    if (body && body.version) $("app-version").textContent = `v${body.version}`;
  } catch (_) {
    setApiStatus("down", "API unreachable");
  } finally {
    clearTimeout(timer);
  }
}

/* ---------- Busy state (prevents double submits) ---------- */
function setBusy(value, analyzing = false) {
  busy = value;
  $("analyze-btn").disabled = value;
  $("upload-btn").disabled = value;
  $("analyze-btn").textContent = value && analyzing ? "Analyzing…" : "Analyze Failure";
}

/* ---------- Upload (the server validates; client checks are for fast feedback) ---------- */
async function loadFile(file) {
  const name = file.name || "";
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".")).toLowerCase() : "";
  if (!ALLOWED_EXTENSIONS.includes(ext)) return setMessage("Only .log, .txt and .out files are accepted.");
  if (file.size > MAX_UPLOAD_BYTES) return setMessage("That file is larger than the 1 MB limit.");
  if (file.size === 0) return setMessage("That file is empty.");

  setBusy(true);
  setMessage("Reading file…", "info");
  try {
    const form = new FormData();
    form.append("file", file); // the browser sets the multipart Content-Type itself
    const data = await apiFetch("/api/upload-log", { method: "POST", body: form }, UPLOAD_TIMEOUT_MS);
    $("log-input").value = data.text;
    updateCounter();
    setMessage(`Loaded ${data.filename} (${data.characters.toLocaleString()} characters).`, "info");
  } catch (err) {
    setMessage(err.message, "error");
  } finally {
    setBusy(false);
  }
}

/* ---------- Analyze ---------- */
async function onAnalyzeClick() {
  if (busy) return;

  const problem = validateInput();
  if (problem) return setMessage(problem, "error");

  setMessage("");
  setBusy(true, true);
  showPanel("panel-loading");
  startLoadingTimer();
  $("panel-loading").scrollIntoView({ behavior: scrollBehavior(), block: "start" });

  try {
    const data = await apiFetch(
      "/api/analyze",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          log_text: $("log-input").value.trim(),
          category: $("category").value,
        }),
      },
      ANALYZE_TIMEOUT_MS,
    );
    currentAnalysisId = data.id;
    renderResult(data);
    refreshHistory(1); // has its own error handling, so it never breaks the result view
  } catch (err) {
    showError(err.message);
  } finally {
    stopLoadingTimer();
    setBusy(false);
  }
}

/* ---------- History ---------- */
function showHistory() {
  renderHistory(historyItems, {
    onOpen: openAnalysis,
    onDelete: deleteAnalysisItem,
    total: historyTotal,
  });
  $("history-more").hidden = historyItems.length >= historyTotal;
}

function showHistoryError(message) {
  historyItems = [];
  historyTotal = 0;
  $("history-list").hidden = true;
  $("history-more").hidden = true;
  $("history-count").textContent = "";
  $("history-empty").hidden = false;
  $("history-empty").querySelector("p").textContent = message;
}

async function loadHistory(limit = HISTORY_PAGE) {
  try {
    const data = await apiFetch(`/api/analyses?limit=${limit}&offset=0`, {}, UPLOAD_TIMEOUT_MS);
    historyItems = data.items;
    historyTotal = data.total;
    $("history-empty").querySelector("p").textContent = HISTORY_EMPTY_TEXT;
    showHistory();
  } catch (err) {
    showHistoryError(`Could not load history. ${err.message}`);
  }
}

// Re-fetch, keeping at least as many rows as the user has already loaded
function refreshHistory(extra = 0) {
  const wanted = Math.min(HISTORY_MAX, Math.max(HISTORY_PAGE, historyItems.length + extra));
  return loadHistory(wanted);
}

async function loadMoreHistory() {
  const btn = $("history-more");
  btn.disabled = true;
  try {
    const data = await apiFetch(
      `/api/analyses?limit=${HISTORY_PAGE}&offset=${historyItems.length}`, {}, UPLOAD_TIMEOUT_MS,
    );
    const seen = new Set(historyItems.map((h) => h.id));
    historyItems = historyItems.concat(data.items.filter((h) => !seen.has(h.id)));
    historyTotal = data.total;
    showHistory();
  } catch (err) {
    toast(`Could not load more: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
  }
}

async function openAnalysis(id) {
  if (busy) return;
  try {
    const data = await apiFetch(`/api/analyses/${id}`, {}, UPLOAD_TIMEOUT_MS);
    data.degraded = data.ai_model === "fallback";
    currentAnalysisId = data.id;
    renderResult(data);
    showHistory();
  } catch (err) {
    if (err.status === 404) {
      await refreshHistory();
      showError("That analysis no longer exists.");
    } else {
      showError(err.message);
    }
  }
}

async function deleteAnalysisItem(id) {
  if (busy) return;
  const confirmed = await confirmDialog({
    title: "Delete this analysis?",
    message: "It will be removed from your history. This cannot be undone.",
    confirmLabel: "Delete",
  });
  if (!confirmed) return;
  try {
    await apiFetch(`/api/analyses/${id}`, { method: "DELETE" }, UPLOAD_TIMEOUT_MS);
  } catch (err) {
    if (err.status !== 404) { // 404 means it is already gone, which is the outcome we wanted
      toast(`Could not delete: ${err.message}`, "error");
      return;
    }
  }
  if (currentAnalysisId === id) {
    currentAnalysisId = null;
    showPanel("panel-empty");
  }
  await refreshHistory();
  toast("Analysis deleted");
}

/* ---------- Sample logs (demo mode) ---------- */
function applySample(sample, { quiet = false } = {}) {
  if (busy) return;
  $("log-input").value = sample.log.trim();
  $("log-input").scrollTop = 0;
  $("category").value = sample.category;
  updateCounter();
  setMessage(`Loaded sample: ${sample.label} (category: ${sample.category}). Select Analyze Failure to run it.`, "info");
  if (!quiet) $("analyze-btn").focus();
}

function initSamples() {
  const samples = Array.isArray(window.SAMPLE_LOGS) ? window.SAMPLE_LOGS : [];
  if (samples.length === 0) return; // the section stays hidden if samples.js failed to load

  const holder = $("sample-buttons");
  for (const sample of samples) {
    holder.append(el("button", {
      type: "button",
      className: "chip",
      text: sample.label,
      title: `${sample.category} sample log`,
      onclick: () => applySample(sample),
    }));
  }
  $("samples").hidden = false;

  // Deep link for demos: /?demo=kubernetes pre-loads that sample (it never auto-analyzes)
  const demo = new URLSearchParams(window.location.search).get("demo");
  if (demo) {
    const match = samples.find((s) => s.id === demo.toLowerCase());
    if (match) applySample(match, { quiet: true });
  }
}

/* ---------- Drag and drop a log file onto the editor ---------- */
function initDropZone() {
  const zone = document.querySelector(".terminal");
  const hasFiles = (e) => e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files");

  // Without this, dropping a file outside the editor makes the browser open it
  window.addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
  window.addEventListener("drop", (e) => { if (hasFiles(e)) e.preventDefault(); });

  zone.addEventListener("dragover", (e) => {
    if (hasFiles(e)) {
      e.preventDefault();
      zone.classList.add("dragging");
    }
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
  zone.addEventListener("drop", async (e) => {
    zone.classList.remove("dragging");
    const file = e.dataTransfer && e.dataTransfer.files[0];
    if (file && !busy) await loadFile(file);
  });
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
  preview: true,
  redactions: 0,
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
  if (mode === "loading") {
    showPanel("panel-loading");
    return startLoadingTimer();
  }
  if (mode === "error") return showError("The AI service took too long to respond. Please try again.");
  if (mode === "redacted") return renderResult({ ...MOCK_RESULT, redactions: 3 });
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
  $("history-more").addEventListener("click", loadMoreHistory);

  initSamples();
  initDropZone();
  updateCounter();
  showPanel("panel-empty");

  checkApiStatus();
  setInterval(checkApiStatus, 60000);

  const preview = new URLSearchParams(window.location.search).get("preview");
  if (preview) runPreview(preview);
  if (preview !== "history") loadHistory();
}

document.addEventListener("DOMContentLoaded", init);
