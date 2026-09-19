"""Run: python app.py. A single-process, loopback-only lead operations demo."""
import argparse
import json
import os
from pathlib import Path
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from adapters import CRMError, HubSpotCRM, LocalCRM, connection, optional_ai, properties

ROOT = Path(__file__).resolve().parent
MAX_ATTEMPTS = 3
FIELDS = {"event_id", "name", "email", "company", "message", "service", "region", "urgency", "demo_outcome"}
FAULTS = {"ok", "rate_limit_once", "rate_limit_always", "auth_error", "timeout_after_write", "timeout_unknown"}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def validate(raw, mode):
    errors, data = [], {}
    for field in FIELDS:
        value = raw.get(field, "ok" if field == "demo_outcome" else "normal" if field == "urgency" else "")
        if not isinstance(value, str):
            errors.append(f"{field} must be text")
            value = ""
        data[field] = value.strip()
    data["email"] = data["email"].lower()
    if set(raw) - FIELDS:
        errors.append("Unknown fields: " + ", ".join(sorted(set(raw) - FIELDS)))
    for field, limit in (("name", 100), ("email", 254), ("company", 150), ("message", 4000)):
        if not data[field] or len(data[field]) > limit:
            errors.append(f"{field} is required and must be at most {limit} characters")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", data["email"]):
        errors.append("email must be a valid address")
    if data["service"] not in ("automation", "analytics", "support"):
        errors.append("Choose a supported service; unclassified inquiries require review")
    if data["region"] not in ("americas", "emea", "apac"):
        errors.append("region must be americas, emea, or apac")
    if data["urgency"] not in ("normal", "urgent"):
        errors.append("urgency must be normal or urgent")
    if data["demo_outcome"] not in FAULTS or (mode != "local" and data["demo_outcome"] != "ok"):
        errors.append("Fault simulation is supported only in local mode")
    return data, errors


class LeadService:
    def __init__(self, db_path, mode="local", crm=None, clock=time.time, rules_path=None):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.clock = clock
        self.rules_path = Path(rules_path or ROOT / "rules.json")
        self.mode = mode
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE,
                    name TEXT, company TEXT, description TEXT, last_event_id TEXT);
            """)
        self.crm = crm or (LocalCRM(self.db_path) if mode == "local" else HubSpotCRM(os.getenv("HUBSPOT_TOKEN")))
        # A process may have stopped between committing intent and recording a response.
        for event in self.events():
            if event["status"] == "processing":
                event["status"] = "reconcile_required"
                event["reason"] = "Process stopped during CRM step. Read back before any further write."
                self.log(event, "recovery", event["reason"])
                self.save(event)

    def db(self):
        return connection(self.db_path)

    def events(self):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT body FROM events ORDER BY rowid DESC")]

    def get(self, event_id):
        with self.db() as db:
            row = db.execute("SELECT body FROM events WHERE id=?", (event_id,)).fetchone()
        if not row:
            raise APIError(404, "Event not found")
        return json.loads(row[0])

    def save(self, event):
        with self.db() as db:
            db.execute("INSERT INTO events VALUES(?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                       (event["id"], json.dumps(event)))

    @staticmethod
    def log(event, action, detail):
        event["logs"].append({"time": now_iso(), "action": action, "detail": detail})

    def prepare(self, event, data, errors):
        event["normalized"] = data
        event["extracted"] = {"summary": " ".join(data["message"].split())[:240],
                              "category": data["service"], "method": "form fields + text excerpt (no AI)"}
        event["owner"], event["routing_reason"] = None, None
        if errors:
            event["status"], event["reason"] = "needs_review", "; ".join(errors)
            self.log(event, "validation", event["reason"])
            return
        try:
            rules = json.loads(self.rules_path.read_text(encoding="utf-8"))
            team = rules[data["service"]]
            if not isinstance(team, str) or not team.strip():
                raise ValueError()
        except (OSError, ValueError, KeyError, TypeError):
            event["status"], event["reason"] = "needs_review", "Routing rules are missing or invalid; fix rules.json and review."
            self.log(event, "routing", event["reason"])
            return
        event["owner"] = f"{team} / {data['region'].upper()}"
        priority = "P1" if data["urgency"] == "urgent" else "P2"
        event["routing_reason"] = f"service={data['service']} → {team}; region={data['region']} → regional queue; urgency={data['urgency']} → {priority}"
        suggestion = optional_ai(data["message"])
        if suggestion:
            event["extracted"]["ai_suggestion"] = suggestion
        event["status"], event["reason"] = "ready", "Validated; routing uses explicit form fields only."
        self.log(event, "routing", event["routing_reason"])

    def submit(self, raw):
        if not isinstance(raw, dict) or not isinstance(raw.get("event_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", raw["event_id"]):
            raise APIError(422, "event_id must be 1–80 letters, digits, underscores or hyphens")
        with self.lock:
            try:
                existing = self.get(raw["event_id"])
            except APIError:
                existing = None
            if existing:
                if existing["raw"] != raw:
                    raise APIError(409, "This event_id already belongs to different input. Use a new event_id for a new inquiry.")
                return {"event": existing, "duplicate": True}
            data, errors = validate(raw, self.mode)
            event = {"id": raw["event_id"], "raw": raw, "normalized": data,
                     "created_at": now_iso(), "status": "ready", "attempts": 0,
                     "next_attempt": None, "contact_id": None, "draft": None, "logs": []}
            self.log(event, "received", "Inquiry captured. Original input retained.")
            self.prepare(event, data, errors)
            self.save(event)
            if event["status"] == "ready":
                event = self.process(event)
            return {"event": event, "duplicate": False}

    def complete(self, event, contact, action):
        event.update(status="completed", reason="Contact read back and confirmed; internal notification draft ready.",
                     contact_id=str(contact["id"]), next_attempt=None)
        p = event["normalized"]
        event["draft"] = f"To: {event['owner']}\nSubject: {p['urgency'].upper()} · {p['company']} · {p['service']}\n\n{p['name']} <{p['email']}>\n{event['extracted']['summary']}\n\nEvent: {event['id']} | Contact: {event['contact_id']}\nDraft only — no message was sent."
        self.log(event, action, f"Contact {event['contact_id']} confirmed. One local draft saved for this event.")
        self.save(event)
        return event

    def archive_older_inquiry(self, event, newer):
        outcome = "already updated this contact" if newer["status"] == "completed" else "has an unconfirmed CRM attempt; inspect that result first"
        event.update(status="archived", next_attempt=None, superseded_by=newer["id"],
                     contact_id=newer.get("contact_id"),
                     reason=f"Newer inquiry {newer['id']} {outcome}. This inquiry is filed and assigned; its older contact details were not written.")
        p = event["normalized"]
        event["draft"] = f"To: {event['owner']}\nSubject: Historical inquiry · {p['company']}\n\n{p['name']} <{p['email']}>\n{event['extracted']['summary']}\n\nEvent: {event['id']}\nContact unchanged; see newer inquiry {newer['id']} for its CRM result.\nDraft only — no message was sent."
        self.log(event, "older_contact_update_skipped", event["reason"])
        self.save(event)
        return event

    def process(self, event):
        # One application process owns the queue; the lock spans the CRM operation.
        events = self.events()
        # Receipt order, not review time, determines which inquiry can update a contact.
        # A newer uncertain write also owns its reconciliation; do not overwrite its marker.
        for newer in events:
            if newer["id"] == event["id"]:
                break
            if (newer["normalized"].get("email") == event["normalized"]["email"]
                    and newer["status"] in ("completed", "processing", "reconcile_required")):
                return self.archive_older_inquiry(event, newer)
        for other in reversed(events):
            if other["id"] == event["id"]:
                break
            pending = other["status"] in ("processing", "reconcile_required", "retry_wait", "blocked_contact", "ready") or (other["status"] == "blocked" and other["attempts"] < MAX_ATTEMPTS)
            if other["normalized"].get("email") == event["normalized"]["email"] and pending:
                event.update(status="blocked_contact", reason=f"Resolve earlier unfinished event {other['id']} for this contact first.")
                self.save(event)
                return event
        if event["attempts"] >= MAX_ATTEMPTS:
            event.update(status="blocked", reason="Three attempts used. Investigate the CRM before submitting a new event.", next_attempt=None)
            self.save(event)
            return event
        event["attempts"] += 1
        event.update(status="processing", next_attempt=None)
        self.log(event, "crm_attempt", f"Attempt {event['attempts']} of {MAX_ATTEMPTS}; {self.mode} CRM.")
        self.save(event)
        try:
            contact = self.crm.sync(event["normalized"], event["attempts"])
            if not contact or "id" not in contact:
                raise CRMError("unknown", "CRM returned no usable contact ID.")
            return self.complete(event, contact, "crm_confirmed")
        except CRMError as exc:
            if exc.kind == "unknown":
                event.update(status="reconcile_required", reason=str(exc))
            elif exc.kind == "transient" and event["attempts"] < MAX_ATTEMPTS:
                delay = max(exc.retry_after, 2 ** event["attempts"])
                event.update(status="retry_wait", reason=str(exc), next_attempt=self.clock() + delay)
            else:
                event.update(status="blocked", reason=str(exc) + (" Retry limit reached." if event["attempts"] >= MAX_ATTEMPTS else ""))
            self.log(event, event["status"], event["reason"])
            self.save(event)
            return event
        except Exception:
            # Unknown adapter errors are never safe evidence for repeating a write.
            event.update(status="reconcile_required", reason="Unexpected CRM failure; read back before any further write.")
            self.log(event, "reconcile_required", event["reason"])
            self.save(event)
            return event

    def retry(self, event_id):
        with self.lock:
            event = self.get(event_id)
            if event["status"] not in ("retry_wait", "blocked", "blocked_contact"):
                raise APIError(409, "Only unfinished, known-safe steps can be retried. Uncertain outcomes require reconciliation.")
            if event["next_attempt"] and self.clock() < event["next_attempt"]:
                raise APIError(409, "Backoff has not elapsed; retry after the displayed due time.")
            return self.process(event)

    def reconcile(self, event_id):
        with self.lock:
            event = self.get(event_id)
            if event["status"] != "reconcile_required":
                raise APIError(409, "Only uncertain CRM outcomes need reconciliation")
            try:
                contact = self.crm.lookup(event["normalized"])
                expected = properties(event["normalized"])
                if contact and all(contact.get("properties", {}).get(k) == v for k, v in expected.items()):
                    return self.complete(event, contact, "reconciled")
                event["reason"] = "Read-back did not match this event and all intended fields. No write repeated. Inspect CRM manually; keep this item unresolved."
            except CRMError:
                event["reason"] = "Read-back unavailable. Outcome remains uncertain; no write repeated."
            self.log(event, "reconciliation_pending", event["reason"])
            self.save(event)
            return event

    def review(self, event_id, changes):
        with self.lock:
            event = self.get(event_id)
            if event["status"] != "needs_review" or event["attempts"]:
                raise APIError(409, "Only input awaiting review can be corrected here")
            if not isinstance(changes, dict) or set(changes) - (FIELDS - {"event_id", "demo_outcome"}):
                raise APIError(422, "Review accepts name, email, company, message, service, region and urgency")
            # Rebuild the supported schema; rejected unknown fields remain in the original input.
            data = dict(event["normalized"])
            data.update(changes)
            data, errors = validate(data, self.mode)
            self.log(event, "human_review", "Operator corrections: " + json.dumps(changes, ensure_ascii=False))
            self.prepare(event, data, errors)
            self.save(event)
            return self.process(event) if event["status"] == "ready" else event

    def process_due(self):
        count = 0
        with self.lock:
            for event in reversed(self.events()):
                if event["status"] in ("ready", "blocked_contact") or (event["status"] == "retry_wait" and event["next_attempt"] <= self.clock()):
                    self.process(event)
                    count += 1
        return {"processed": count}

    def dashboard(self):
        events = self.events()
        with self.db() as db:
            contacts = [dict(r) for r in db.execute("SELECT * FROM contacts ORDER BY id DESC")]
        # In HubSpot mode expose only IDs already confirmed through this application.
        total_contacts = len(contacts) if self.mode == "local" else len({e["contact_id"] for e in events if e["contact_id"]})
        return {"events": events, "contacts": contacts if self.mode == "local" else [],
                "mode": self.mode, "ai_mode": "configured" if os.getenv("AI_URL") and os.getenv("AI_MODEL") else "disabled",
                "stats": {"total": len(events), "completed": sum(e["status"] in ("completed", "archived") for e in events),
                          "review": sum(e["status"] in ("needs_review", "blocked", "reconcile_required") for e in events),
                          "waiting": sum(e["status"] in ("retry_wait", "blocked_contact", "processing") for e in events), "contacts": total_contacts}}


def handler_for(service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # No lead content, tokens, or raw remote responses in access logs.

        def send_json(self, body, status=200):
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            try:
                if path == "/api/dashboard":
                    return self.send_json(service.dashboard())
                if path == "/api/events":
                    return self.send_json({"events": service.events()})
                if path.startswith("/api/events/"):
                    return self.send_json(service.get(path.rsplit("/", 1)[-1]))
                files = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
                if path not in files:
                    raise APIError(404, "Not found")
                filename, mime = files[path]
                data = (ROOT / "static" / filename).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime + "; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)
            except APIError as exc:
                self.send_json({"error": exc.message}, exc.status)

        def do_POST(self):
            try:
                origin = self.headers.get("Origin")
                allowed = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
                if origin and origin not in allowed:
                    raise APIError(403, "Cross-origin writes are not allowed")
                if self.headers.get_content_type() != "application/json":
                    raise APIError(415, "Use Content-Type: application/json")
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 32768:
                    raise APIError(413, "JSON request must be 1–32768 bytes")
                body = json.loads(self.rfile.read(length))
                path = unquote(urlparse(self.path).path)
                if path == "/api/leads":
                    return self.send_json(service.submit(body))
                if path == "/api/process-due":
                    return self.send_json(service.process_due())
                match = re.fullmatch(r"/api/events/([A-Za-z0-9_-]+)/(?P<action>retry|reconcile|review)", path)
                if match:
                    event_id, action = match.group(1), match.group("action")
                    result = service.review(event_id, body) if action == "review" else getattr(service, action)(event_id)
                    return self.send_json(result)
                raise APIError(404, "Not found")
            except APIError as exc:
                self.send_json({"error": exc.message}, exc.status)
            except (ValueError, UnicodeError):
                self.send_json({"error": "Invalid JSON request"}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=str(ROOT / "data" / "leads.db"))
    parser.add_argument("--mode", choices=("local", "hubspot"), default="local")
    args = parser.parse_args()
    service = LeadService(args.db, args.mode)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(service))
    print(f"Lead operations desk: http://127.0.0.1:{args.port} | CRM: {args.mode}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
