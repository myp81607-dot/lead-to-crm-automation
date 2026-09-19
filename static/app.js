"use strict";

const state = { events: [], contacts: [], stats: {}, mode: "local", selectedId: null, filter: "all", view: "queue", reviewId: null, busy: false };
const byId = id => document.getElementById(id);
const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const labels = { completed: "Complete", needs_review: "Needs review", retry_wait: "Retry scheduled", blocked: "Blocked", reconcile_required: "Verify result", blocked_contact: "Contact held" };
const attentionStatuses = new Set(["needs_review", "blocked", "reconcile_required", "blocked_contact"]);
const serviceLabels = { automation: "Automation", analytics: "Analytics", support: "Support", unsure: "Needs scoping" };
const regionLabels = { americas: "Americas", emea: "EMEA", apac: "APAC" };
let toastTimer;

function pretty(value) { return String(value ?? "").replace(/_/g, " "); }
function asDate(value) { if (!value) return null; const date = new Date(typeof value === "number" ? value * (value < 1e12 ? 1000 : 1) : value); return Number.isNaN(date.getTime()) ? null : date; }
function time(value) { const date = asDate(value); return date ? date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "—"; }
function dateTime(value) { const date = asDate(value); return date ? date.toLocaleString("en-GB", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"; }
function initials(name) { return String(name || "?").trim().split(/\s+/).slice(0, 2).map(part => part[0] || "").join("").toUpperCase(); }
function dataFor(event) { return { ...(event.raw || {}), ...(event.normalized || {}) }; }
function eventId(event) { return String(event.id); }
function statusHTML(status) { const safeStatus = Object.hasOwn(labels, status) ? status : "unknown"; return `<span class="status ${safeStatus}">${escapeHTML(labels[status] || pretty(status) || "Pending")}</span>`; }
function toast(message, error = false) { clearTimeout(toastTimer); const el = byId("toast"); el.textContent = message; el.classList.toggle("error", error); el.hidden = false; toastTimer = setTimeout(() => { el.hidden = true; }, 6000); }

async function api(path, data) {
  const options = data === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) };
  const response = await fetch(path, options);
  let result;
  try { result = await response.json(); } catch { throw new Error(`Server returned ${response.status}. Check that the backend is running.`); }
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
  return result;
}

async function refresh(quiet = false) {
  try {
    const dashboard = await api("/api/dashboard");
    state.events = dashboard.events || [];
    state.contacts = dashboard.contacts || [];
    state.stats = dashboard.stats || {};
    state.mode = dashboard.mode || "local";
    if (!state.selectedId && state.events.length) state.selectedId = eventId(state.events[0]);
    byId("mode-label").textContent = state.mode === "hubspot" ? "HubSpot mode" : "Local CRM mode";
    byId("connection-dot").classList.remove("offline");
    byId("rules-label").textContent = dashboard.ai_mode === "configured" ? "AI configured · see extraction method" : "Rules extraction · AI off";
    byId("simulation-box").hidden = state.mode !== "local" || Boolean(state.reviewId);
    byId("demo-outcome").disabled = state.mode !== "local";
    ["total", "completed", "review", "contacts"].forEach(key => { byId(`stat-${key}`).textContent = state.stats[key] ?? 0; });
    byId("nav-total").textContent = state.stats.total ?? state.events.length;
    byId("queue-count").textContent = state.events.length;
    byId("waiting-count").textContent = `${state.stats.waiting ?? 0} waiting`;
    byId("last-refreshed").textContent = `Updated ${time(Date.now())}`;
    renderQueue();
    renderDetail();
    renderContacts();
    return true;
  } catch (error) {
    byId("connection-dot").classList.add("offline");
    byId("mode-label").textContent = "Connection unavailable";
    byId("last-refreshed").textContent = "Refresh failed — shown data may be stale";
    if (!state.events.length) byId("queue-list").innerHTML = `<div class="empty-state"><span class="empty-icon">!</span><h3>Cannot load the queue</h3><p>${escapeHTML(error.message)}</p><button class="button secondary" data-action="refresh">Try again</button></div>`;
    if (!quiet) toast(error.message, true);
    return false;
  }
}

function showView(view) {
  state.view = view;
  ["queue", "contacts", "intake"].forEach(name => { byId(`${name}-view`).hidden = name !== view; });
  document.querySelectorAll("[data-view]").forEach(button => button.classList.toggle("active", button.dataset.view === view));
  byId("breadcrumb-current").textContent = { queue: "Lead queue", contacts: "Contacts", intake: state.reviewId ? "Correct inquiry" : "New inquiry" }[view];
  byId("page-title").textContent = { queue: "A clear queue. A better handoff.", contacts: "The right context, in one place.", intake: "Start with a real inquiry." }[view];
  byId("page-subtitle").textContent = { queue: "Capture the inquiry, find the right owner, and keep the contact up to date.", contacts: "See the contact records created and updated by the processing queue.", intake: "Follow one request from the form to an explained, traceable outcome." }[view];
  byId("new-lead-button").hidden = view === "intake";
}

function renderQueue() {
  const visible = state.events.filter(event => state.filter === "all" || (state.filter === "attention" ? attentionStatuses.has(event.status) : event.status === "completed"));
  if (!visible.length) {
    byId("queue-list").innerHTML = `<div class="empty-state"><span class="empty-icon">${state.events.length ? "✓" : "↘"}</span><h3>${state.events.length ? "Nothing in this view" : "Your next lead starts here"}</h3><p>${state.events.length ? "Choose another filter to see the rest of the queue." : "Submit a sample inquiry to see validation, routing, and a contact update in action."}</p>${state.events.length ? "" : '<button class="button primary" data-action="new-sample">Try a sample inquiry</button>'}</div>`;
    return;
  }
  byId("queue-list").innerHTML = visible.map(event => {
    const lead = dataFor(event);
    const summary = event.extracted?.summary || lead.message || event.reason || "This inquiry needs a closer look.";
    return `<button class="lead-card ${eventId(event) === state.selectedId ? "selected" : ""}" data-event="${escapeHTML(eventId(event))}" aria-pressed="${eventId(event) === state.selectedId}"><div class="lead-card-header"><span class="person-avatar">${escapeHTML(initials(lead.name))}</span><span class="lead-identity"><strong>${escapeHTML(lead.name || "Unnamed inquiry")}</strong><span>${escapeHTML(lead.company || lead.email || "Awaiting details")}</span></span>${statusHTML(event.status)}</div><p class="lead-summary">${escapeHTML(summary)}</p><div class="lead-meta"><span>${escapeHTML(serviceLabels[lead.service] || "To be reviewed")}</span><span>${escapeHTML(event.owner || "Unassigned")}</span><time>${escapeHTML(dateTime(event.created_at))}</time></div></button>`;
  }).join("");
}

function renderDetail() {
  const event = state.events.find(item => eventId(item) === state.selectedId);
  if (!event) {
    byId("detail-panel").innerHTML = '<div class="empty-state detail-empty"><span class="empty-icon">↗</span><h3>Every lead, in context.</h3><p>Select an inquiry to see its owner, CRM update, and processing history.</p></div>';
    return;
  }
  const lead = dataFor(event);
  const isComplete = event.status === "completed";
  const needsAction = attentionStatuses.has(event.status);
  const reason = event.reason || (isComplete ? "The contact was saved and a local follow-up draft is ready." : "See the processing history for the current result.");
  const actionButtons = [];
  if (event.status === "needs_review") actionButtons.push('<button class="button primary" data-action="review">Correct & resubmit</button>');
  if (["blocked", "retry_wait", "blocked_contact"].includes(event.status)) actionButtons.push('<button class="button secondary" data-action="retry">Retry processing</button>');
  if (event.status === "reconcile_required") actionButtons.push('<button class="button primary" data-action="reconcile">Verify CRM result</button>');
  actionButtons.push('<button class="button secondary" data-action="replay">Replay original event</button>');
  const logs = (event.logs || []).map(log => `<li><div class="timeline-heading"><span>${escapeHTML(pretty(log.action))}</span><time>${escapeHTML(time(log.time))}</time></div><p>${escapeHTML(typeof log.detail === "object" ? JSON.stringify(log.detail) : log.detail)}</p></li>`).join("");
  const reviewText = event.status === "reconcile_required" ? "Verification only reads the CRM. It does not send the inquiry again." : event.status === "blocked_contact" ? "Another event for this contact has an unresolved result. Resolve that event before retrying this one." : "";
  byId("detail-panel").innerHTML = `<div class="detail-header"><div class="detail-topline"><span class="detail-kicker">INQUIRY DETAILS</span>${statusHTML(event.status)}</div><h2>${escapeHTML(lead.name || "Unnamed inquiry")}</h2><p class="detail-company">${escapeHTML(lead.company || "Company not supplied")}<span>·</span>${escapeHTML(regionLabels[lead.region] || "Region not supplied")}${lead.urgency === "urgent" ? "<span>·</span>Urgent" : ""}</p><p class="detail-contact-line">${escapeHTML(lead.email || "Email needs review")}</p></div><div class="detail-content"><section class="detail-section"><div class="detail-label">THE REQUEST</div><p class="detail-message">${escapeHTML(lead.message || "No message provided.")}</p></section><section class="detail-section routing-box"><div><span>Assigned owner</span><strong>${escapeHTML(event.owner || "Awaiting review")}</strong></div><div><span>Service</span><strong>${escapeHTML(serviceLabels[lead.service] || "To be reviewed")}</strong></div><p class="routing-reason">${escapeHTML(event.routing_reason || "Routing runs after the input passes validation.")}</p></section><section class="detail-section outcome-box ${needsAction ? (event.status === "blocked" ? "error" : "warning") : !isComplete ? "warning" : ""}"><div class="outcome-title"><span aria-hidden="true">${isComplete ? "✓" : "!"}</span>${escapeHTML(isComplete ? "Contact updated" : labels[event.status] || pretty(event.status))}</div><p>${escapeHTML(reason)}</p>${event.contact_id ? `<p>Confirmed CRM contact: ${escapeHTML(event.contact_id)}</p>` : ""}${event.next_attempt ? `<p>Next attempt: ${escapeHTML(dateTime(event.next_attempt))}</p>` : ""}${reviewText ? `<p>${escapeHTML(reviewText)}</p>` : ""}<div class="detail-actions">${actionButtons.join("")}</div></section>${event.draft ? `<section class="detail-section"><div class="detail-label">FOLLOW-UP DRAFT · SAVED LOCALLY, NOT SENT</div><div class="draft-text">${escapeHTML(event.draft)}</div></section>` : ""}${event.extracted ? `<details class="detail-disclosure"><summary>Extraction <span>${escapeHTML(pretty(event.extracted.method || "rules"))}</span></summary><p class="detail-message">${escapeHTML(event.extracted.summary || "No summary available.")}</p>${event.extracted.ai_suggestion ? `<pre class="raw-payload">${escapeHTML(JSON.stringify(event.extracted.ai_suggestion, null, 2))}</pre>` : ""}</details>` : ""}<details class="detail-disclosure" open><summary>Processing history <span>${(event.logs || []).length} entries</span></summary><ol class="timeline">${logs || '<li><p>No history recorded yet.</p></li>'}</ol></details><details class="detail-disclosure"><summary>Original submission</summary><pre class="raw-payload">${escapeHTML(JSON.stringify(event.raw || {}, null, 2))}</pre></details><div class="event-metadata"><code>${escapeHTML(lead.event_id || event.id)}</code><span>${escapeHTML(event.attempts ?? 0)} CRM attempt${event.attempts === 1 ? "" : "s"}</span></div></div>`;
}

function renderContacts() {
  if (state.mode === "hubspot") { byId("contacts-list").innerHTML = '<div class="empty-state"><span class="empty-icon">↗</span><h3>Contacts live in HubSpot</h3><p>This workspace records confirmed CRM contact IDs on each inquiry. It does not load your full HubSpot contact directory.</p></div>'; return; }
  if (!state.contacts.length) { byId("contacts-list").innerHTML = '<div class="empty-state"><span class="empty-icon">♧</span><h3>No contacts yet</h3><p>A successful inquiry creates or updates a contact here.</p></div>'; return; }
  byId("contacts-list").innerHTML = `<table class="contacts-table"><thead><tr><th>CONTACT</th><th>COMPANY</th><th>LATEST CONTEXT</th><th>CRM ID</th></tr></thead><tbody>${state.contacts.map(contact => `<tr><td><strong>${escapeHTML(contact.name || "Unnamed contact")}</strong><small>${escapeHTML(contact.email)}</small></td><td>${escapeHTML(contact.company || "—")}</td><td class="description">${escapeHTML(contact.description || "—")}</td><td><span class="contact-table-id">${escapeHTML(contact.id)}</span></td></tr>`).join("")}</tbody></table>`;
}

function startIntake() {
  state.reviewId = null;
  byId("intake-form").reset();
  byId("event-id").value = `web-${Date.now()}`;
  byId("event-id").readOnly = false;
  byId("intake-title").textContent = "Create an inquiry";
  byId("intake-subtitle").textContent = "Use the form as a website visitor would.";
  byId("submit-lead-button").textContent = "Submit inquiry →";
  byId("fill-sample-button").hidden = false;
  byId("fill-failure-button").hidden = false;
  byId("simulation-box").hidden = state.mode !== "local";
  byId("form-error").hidden = true;
  showView("intake");
}

function fillSample(failure = false) {
  startIntake();
  const values = { name: "Jamie Morgan", email: failure ? "jamie-at-example.com" : "jamie@example.com", company: "Northstar Studio", message: failure ? "We need a clearer handoff from our website inquiries to our sales team. Please help us connect the form and CRM." : "Our team manually copies website inquiries into the CRM. We need to route new leads by service and region, keep one contact per email, and flag requests that need review.", service: "automation", region: "emea", urgency: "normal", demo_outcome: "ok" };
  for (const [key, value] of Object.entries(values)) byId("intake-form").elements.namedItem(key).value = value;
  byId("event-id").value = `${failure ? "review" : "demo"}-${Date.now()}`;
  toast(failure ? "Review example loaded. Submit it to see server-side validation." : "Synthetic inquiry loaded. Edit any field, then submit.");
}

function startReview() {
  const event = state.events.find(item => eventId(item) === state.selectedId);
  if (!event || event.status !== "needs_review") return;
  startIntake();
  state.reviewId = eventId(event);
  const lead = dataFor(event);
  for (const key of ["event_id", "name", "email", "company", "message", "service", "region", "urgency"]) {
    const field = byId("intake-form").elements.namedItem(key);
    field.value = lead[key] ?? "";
  }
  byId("event-id").readOnly = true;
  byId("intake-title").textContent = "Correct the inquiry";
  byId("intake-subtitle").textContent = "The original submission stays in the audit trail.";
  byId("submit-lead-button").textContent = "Save correction & process →";
  byId("fill-sample-button").hidden = true;
  byId("fill-failure-button").hidden = true;
  byId("simulation-box").hidden = true;
  showView("intake");
}

async function runAction(action, button) {
  if (state.busy) return;
  const event = state.events.find(item => eventId(item) === state.selectedId);
  if (action === "refresh") return refresh();
  if (action === "new-sample") return fillSample();
  if (action === "review") return startReview();
  if (!event && action !== "process-due") return;
  state.busy = true;
  if (button) button.disabled = true;
  try {
    if (action === "replay") {
      const result = await api("/api/leads", event.raw || {});
      state.selectedId = result.event ? eventId(result.event) : state.selectedId;
      toast(result.duplicate ? "Duplicate event recognized. No second inquiry was created." : "Original event submitted.");
    } else if (action === "process-due") {
      await api("/api/process-due", {});
      toast("Due retries processed. The queue shows the current result.");
    } else {
      const result = await api(`/api/events/${encodeURIComponent(state.selectedId)}/${action}`, {});
      if (result.event) state.selectedId = eventId(result.event);
      toast(action === "reconcile" ? "CRM verification finished. Check the recorded result." : "Retry finished. Check the recorded result.");
    }
    await refresh();
  } catch (error) { toast(error.message, true); await refresh(true); }
  finally { state.busy = false; if (button?.isConnected) button.disabled = false; }
}

document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => { if (button.dataset.view === "intake") startIntake(); else showView(button.dataset.view); }));
document.querySelectorAll("[data-filter]").forEach(button => button.addEventListener("click", () => { state.filter = button.dataset.filter; document.querySelectorAll("[data-filter]").forEach(item => item.classList.toggle("active", item === button)); renderQueue(); }));
byId("new-lead-button").addEventListener("click", startIntake);
byId("cancel-intake-button").addEventListener("click", () => showView("queue"));
byId("fill-sample-button").addEventListener("click", () => fillSample());
byId("fill-failure-button").addEventListener("click", () => fillSample(true));
byId("refresh-button").addEventListener("click", () => refresh());
byId("process-due-button").addEventListener("click", event => runAction("process-due", event.currentTarget));
document.addEventListener("click", event => {
  const card = event.target.closest("[data-event]");
  if (card) { state.selectedId = card.dataset.event; renderQueue(); renderDetail(); }
  const actionButton = event.target.closest("[data-action]");
  if (actionButton) runAction(actionButton.dataset.action, actionButton);
});

byId("intake-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (state.busy) return;
  state.busy = true;
  const submitButton = byId("submit-lead-button");
  submitButton.disabled = true;
  byId("form-error").hidden = true;
  const values = Object.fromEntries(new FormData(event.currentTarget));
  if (state.mode !== "local") delete values.demo_outcome;
  const reviewId = state.reviewId;
  try {
    let result;
    if (reviewId) {
      delete values.event_id;
      delete values.demo_outcome;
      result = await api(`/api/events/${encodeURIComponent(reviewId)}/review`, values);
    } else result = await api("/api/leads", values);
    if (result.event) state.selectedId = eventId(result.event);
    state.reviewId = null;
    state.filter = "all";
    document.querySelectorAll("[data-filter]").forEach(button => button.classList.toggle("active", button.dataset.filter === "all"));
    await refresh();
    showView("queue");
    toast(result.duplicate ? "This event was already received. Showing the existing inquiry." : result.event?.status === "needs_review" ? "Inquiry saved for human review. Correct the flagged input to continue." : "Inquiry processed. Its outcome is recorded in the queue.");
  } catch (error) {
    byId("form-error").textContent = error.message;
    byId("form-error").hidden = false;
  } finally { state.busy = false; submitButton.disabled = false; }
});

refresh();
