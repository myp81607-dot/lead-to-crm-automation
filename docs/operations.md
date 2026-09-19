# Operation and integration details

[English overview](../README.md) · [中文概览](../README.zh-CN.md)

## Local operation

`python app.py` binds only to `127.0.0.1:8765`. Use one process per database. SQLite persists inquiries and local contacts under `data/`; stopping the server does not erase them. The UI button **Process due retries**, the API, or the n8n schedule can advance due work. There is no hidden background retry worker.

Change [rules.json](../rules.json) to rename a service's team. The next validated inquiry reads the file again. Region appends a regional queue, and urgency maps to P1/P2 in the explanation. These are synthetic operating rules, not learned predictions or real employee assignments. Existing assignments retain the rule result used at the time.

## Input and API

Use `Content-Type: application/json`. Requests are limited to 32 KiB; event IDs must contain 1–80 letters, digits, underscores or hyphens. That stable envelope is necessary to store and replay an inquiry. A malformed ID is rejected with 422. Other invalid fields produce a stored `needs_review` event with reasons and no CRM attempt.

Required fields: `name` (1–100 characters), `email` (basic address syntax, at most 254), `company` (1–150), `message` (1–4000), `service` (`automation`, `analytics`, `support`; `unsure` goes to review), `region` (`americas`, `emea`, `apac`). `urgency` defaults to `normal`, with `urgent` also supported. Whitespace is trimmed; email is lowercased. Unknown fields require review. Email syntax validation does not prove mailbox ownership or deliverability.

```sh
curl -X POST http://127.0.0.1:8765/api/leads -H "Content-Type: application/json" --data-binary @examples/lead.json
```

In Windows PowerShell, use `curl.exe` or:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8765/api/leads' -ContentType 'application/json' -InFile 'examples/lead.json'
```

| Endpoint | Result |
| --- | --- |
| `POST /api/leads` | `{event, duplicate}`. HTTP 200 means stored, not necessarily CRM-complete. Exact replay returns the stored result; altered content with the same ID returns 409. |
| `GET /api/dashboard` | Events, local contact records, totals, adapter mode and whether AI is configured. No tokens. |
| `GET /api/events` | `{events: [...]}` |
| `GET /api/events/{event_id}` | One event, including original input, normalized fields, extraction, routing, attempts, history and draft. |
| `POST /api/events/{event_id}/review` | Correct supported fields on an unattempted `needs_review` event. Original input stays intact; corrections are recorded. |
| `POST /api/events/{event_id}/retry` | Retry a known-safe unfinished CRM step after its due time; never an uncertain write. Body `{}`. |
| `POST /api/events/{event_id}/reconcile` | Read the CRM and compare all intended properties plus the event marker; no write. Body `{}`. |
| `POST /api/process-due` | One ordered pass over due retries and waiting same-contact events. Body `{}`. |

## Recovery decisions

| State | Meaning and next step |
| --- | --- |
| `completed` | Contact read-back confirmed. Exactly one local draft stored on the event. |
| `archived` | An older inquiry was reviewed after a newer inquiry updated this email or began an uncertain write. It is assigned and filed, with a historical draft, but does not write its older fields. `superseded_by` links to the newer inquiry. |
| `needs_review` | Missing/invalid fields or unavailable routing rules. Correct input in the UI. |
| `retry_wait` | Known temporary rejection or failed read before writing. Wait at least 2 then 4 seconds; HubSpot `Retry-After` can extend the wait. At most three CRM attempts per event. |
| `blocked` | Credential/configuration rejection, or retry budget exhausted. No scheduled retry. Correct external configuration before a manual retry; after three attempts, investigate and use a new event only for a known-safe corrective request. |
| `blocked_contact` | An earlier event for the same email has not completed. Resolve it first. Later inquiries cannot overtake a pending retry. |
| `reconcile_required` | A write may have succeeded, or the process stopped while executing it. Read back; do not automatically create or resend. |

429 is treated as a known rejection. A write timeout, write 5xx, conflict or failed post-write read-back is uncertain. A 401/403 is operator-blocked. Read-only failures are safe to retry within the same bound. Each attempt's intent is persisted before the CRM call. Local fault modes explicitly simulate these outcomes; they do not fake a live HubSpot response.

Read-back must match email, name, company and description (which contains `[lead-event:EVENT_ID]` and original message). Missing or different data remains uncertain. A later external edit can therefore prevent automatic confirmation. The operator must inspect HubSpot and resolve the discrepancy externally; this small demo intentionally provides no force-complete or force-create action. A terminal known-safe failure with three used attempts cannot write again, so a later new event may proceed.

No exactly-once guarantee is claimed across arbitrary external systems. Event deduplication is local; the contact marker and read-back comparison constrain recovery. The app is single-process, and the review UI is local rather than an authenticated multi-user audit system.

The Handled total includes `completed` and `archived` inquiries; it is not a count of CRM writes. Current contact details in the local UI come from the contacts table, while the selected inquiry displays its own historical input. In HubSpot mode the full contact directory is not mirrored locally.

### Try the older-review case

With the local server running, load the two [review-ordering examples](../examples/review-ordering.json):

```sh
python demo.py --scenario review-ordering
```

Open `review-old-001` and correct only Service to Automation. `review-new-001` has already saved New company. The older inquiry becomes `archived`, has zero CRM attempts, keeps its own owner and historical draft, and points to the newer inquiry. Company, description and `last_event_id` remain from the newer request. If the old email is corrected to a different contact without a newer inquiry, normal synchronization proceeds.

Only a newer confirmed update or uncertain/in-progress write causes this skip. New valid inquiries are not blocked by old `needs_review` items. Existing known-safe retries still execute in receipt order. If a newer write is uncertain, the UI says so; archiving the old inquiry does not confirm that write. Receipt order is the SQLite insertion order, not the time an operator corrected a form. A fresh database is needed to repeat the example from its initial state; an exact replay returns its already saved result.

## HubSpot adapter — live verification outstanding

Use a separate, authorized HubSpot test account. The operator supplies a private app access token with `crm.objects.contacts.read` and `crm.objects.contacts.write` scopes; store it only in an environment variable. Never paste it into the UI, fixtures, screenshots or Git. The app does not provision tokens or accounts.

Set `HUBSPOT_TOKEN` in your shell's environment, then run:

```sh
python app.py --mode hubspot --db data/hubspot-test.db
```

Always use a different database from local mode. The adapter reads a contact by email, PATCHes an existing ID or POSTs a new contact, then reads it back. It writes `email`, `firstname` (the supplied full name, deliberately not guessed into components), `company`, and `description`. **Description is replaced with the latest inquiry and event marker**, so use only a designated test account/contact until a real project's field mapping is agreed. Local assignment does not set `hubspot_owner_id`. The app does not mirror the whole HubSpot directory; confirmed IDs appear on event details.

Before calling the integration verified, create one synthetic contact, read it back, replay the exact event, then submit a new event for the same email and verify the update in the authorized test account. The included offline contract test does not substitute for these checks. No live verification was performed for this portfolio version. Fault simulation and `demo.py` seeding are disabled outside local mode.

## Optional AI — advisory, not connected in the demo

With `AI_URL` (complete chat-completions endpoint URL) and `AI_MODEL` set, the app makes one advisory request per validation pass. Set `AI_API_KEY` only if that endpoint requires it. No endpoint or paid model is selected automatically. Clear those variables for deterministic, zero-model-call behavior.

The model receives the inquiry text and a fixed instruction to return a summary and one allowed category. It receives no CRM token, tools or local files. The response must be a JSON object with `summary` up to 240 characters and an allowed `category`. A timeout, bad shape or invalid field is labeled unavailable. The raw inquiry and deterministic text excerpt remain visible; explicit form fields continue to determine the owner. The model's answer is displayed as an unverified suggestion, not a confidence score.

Only disabled mode and failure/shape handling were validated offline. Live quality, latency, pricing and provider data handling have not been measured. Enable a provider only with authorization for the inquiry data and potential usage fees. There is no automatic paid fallback.

## Maintenance boundary

An actual team deployment needs its own authorized CRM field mapping and ownership rules, authentication, hosting/network configuration, retention/backup policy and operational owner. Keep the database and credentials private. This repository does not provide a public service, cold outreach, marketing, payments or CRM-wide administration.
