"""Exercise a published LOCAL n8n workflow using synthetic inquiries.

Run with both services on the same host. Leave the backend in local mode and
do not click Process due / Retry while this check waits for the schedule.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
import uuid


def request(url, body=None):
    payload = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        response = urllib.request.urlopen(req, timeout=70)
    except urllib.error.HTTPError as exc:
        response = exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"FAIL: could not connect: {exc.reason}. Check that both local services are running.") from None
    with response:
        try:
            return response.status, json.load(response)
        except json.JSONDecodeError:
            raise SystemExit(f"FAIL: HTTP {response.status} did not contain JSON. Wait for n8n's "
                             "'Activated workflow' startup message and check its execution log.") from None


def require(condition, message):
    if not condition:
        raise SystemExit("FAIL: " + message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--webhook", default="http://127.0.0.1:5678/webhook/lead-intake-demo")
    parser.add_argument("--backend", default="http://127.0.0.1:8765")
    parser.add_argument("--wait", type=int, default=100, help="Seconds allowed for the minute schedule")
    args = parser.parse_args()
    for url in (args.webhook, args.backend):
        require(urlparse(url).hostname in ("127.0.0.1", "localhost", "::1"),
                "this synthetic check accepts loopback URLs only")
    status, dashboard = request(args.backend + "/api/dashboard")
    require(status == 200 and dashboard.get("mode") == "local", "backend must be in local CRM mode")

    run = "n8n-" + uuid.uuid4().hex[:12]
    lead = {
        "event_id": run + "-first", "name": "Morgan Example",
        "email": run + "@example.com", "company": "Example Studio",
        "message": "Please route our website inquiries to the workflow team.",
        "service": "automation", "region": "apac", "urgency": "normal",
    }
    status, first = request(args.webhook, lead)
    require(status == 200 and first.get("duplicate") is False and
            first.get("event", {}).get("status") == "completed", "first inquiry must complete with HTTP 200")
    contact_id = first["event"]["contact_id"]
    print(f"PASS create: {lead['event_id']} -> contact {contact_id}", flush=True)

    status, replay = request(args.webhook, lead)
    require(status == 200 and replay.get("duplicate") is True and
            replay["event"]["attempts"] == first["event"]["attempts"], "exact replay must not repeat a CRM attempt")
    print("PASS exact replay: duplicate=true, attempts unchanged", flush=True)

    status, collision = request(args.webhook, {**lead, "company": "Changed input"})
    require(status == 409 and "error" in collision, "same ID with changed input must preserve HTTP 409")
    print("PASS collision: HTTP 409 with backend error body", flush=True)

    status, invalid = request(args.webhook, {})
    require(status == 422 and "error" in invalid, "invalid envelope must preserve HTTP 422")
    print("PASS invalid envelope: HTTP 422 with backend error body", flush=True)

    update = {**lead, "event_id": run + "-update", "company": "Updated Example Studio",
              "message": "Add an analytics handoff to this inquiry.", "service": "analytics"}
    status, second = request(args.webhook, update)
    require(status == 200 and second["event"]["status"] == "completed" and
            second["event"]["contact_id"] == contact_id, "a new inquiry for the same email must update the same contact")
    _, dashboard = request(args.backend + "/api/dashboard")
    contact = next(c for c in dashboard["contacts"] if c["email"] == lead["email"])
    require(contact["company"] == update["company"] and contact["last_event_id"] == update["event_id"] and
            update["message"] in contact["description"], "read-back must contain the new contact values")
    print("PASS update and read-back: same contact, new company/message/event", flush=True)

    retry = {**lead, "event_id": run + "-retry", "email": run + "-retry@example.com",
             "demo_outcome": "rate_limit_once"}
    status, waiting = request(args.webhook, retry)
    event = waiting.get("event", {})
    require(status == 200 and event.get("status") == "retry_wait" and event["attempts"] == 1,
            "simulated first-write rejection must remain pending")
    started = time.monotonic()
    print(f"WAIT schedule: {retry['event_id']} is retry_wait; no manual retry request will be sent", flush=True)
    while time.monotonic() - started < args.wait:
        time.sleep(2)
        _, event = request(args.backend + "/api/events/" + retry["event_id"])
        if event["status"] == "completed":
            require(event["attempts"] == 2, "scheduled recovery must complete on attempt 2")
            print(f"PASS due retry: completed on attempt 2 after {time.monotonic() - started:.1f}s", flush=True)
            print("Check n8n Executions for the matching Every minute -> Process due work run.", flush=True)
            return
    raise SystemExit("FAIL: minute schedule did not complete the pending event within the wait window")


if __name__ == "__main__":
    main()
