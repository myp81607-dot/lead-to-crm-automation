# References and original implementation

Personal demonstration using synthetic inquiries. Sources reviewed on 2026-09-19. The links below inform the implementation; they do not establish that a live CRM, model, or n8n instance has been tested.

| Source | What informed this project |
| --- | --- |
| [n8n HubSpot node documentation](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.hubspot/) | Evaluated native contact create/update, lookup and search operations. This demo keeps CRM operations inside the backend adapter so one component owns deduplication and recovery. |
| [Capture website leads to HubSpot or Google Sheets with Slack follow-up](https://n8n.io/workflows/12374-capture-website-leads-to-hubspot-or-google-sheets-with-slack-follow-up/), by Mohammad Abubakar | Conceptual reference for webhook intake, normalization, email-based contact lookup and team follow-up. We did not import or copy the template JSON, code, screenshots or text. This project omits enrichment, Google Sheets and live message sending. |
| [n8n Webhook](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/) | POST intake, test versus production URLs, and response-node mode. |
| [n8n HTTP Request](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/) | JSON request bodies, full response status, non-2xx forwarding, and request timeout configuration. |
| [n8n Respond to Webhook](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.respondtowebhook/) | Returning the backend's actual JSON and HTTP code; an execution that errors before responding returns an error. |
| [n8n Schedule Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/) | One-minute periodic trigger, explicit workflow timezone and activation requirement. |
| [HubSpot CRM Contacts guide](https://developers.hubspot.com/docs/api-reference/legacy/crm/objects/contacts/guide) | Contact properties and create/read/update API behavior, including email as a lookup identifier. The adapter must still be verified against an authorized test account before claiming a live integration. |

The repository's original work includes its API, local persistent processing queue, separate event and contact deduplication, rule-based assignment with reasons, explicit failure/review states, local notification drafts, UI, synthetic examples, tests and the small n8n orchestration export. AI-assisted development was used; implementation claims are bounded by the actual tests reported in the README.

## Source and license boundaries

No third-party application code, template workflow, images or sample business data was vendored from the above sources. The workflow JSON here was authored for this repository's own API contract; referring to node names and parameter fields does not include the n8n runtime.

The n8n template page identifies its creator and offers use through n8n, but it does not present a separate permissive license for copying its implementation into this repository. We therefore used its publicly described process only as a reference. Its authorship remains attributed above.

The n8n runtime is governed by its own [license](https://github.com/n8n-io/n8n/blob/master/LICENSE.md), including the Sustainable Use License and separately licensed enterprise portions. This repository's license does not relicense n8n or the referenced documentation. Install n8n separately under its applicable terms.

For export field verification, we inspected the official source definitions for [HTTP Request](https://github.com/n8n-io/n8n/blob/master/packages/nodes-base/nodes/HttpRequest/V3/Description.ts), [Respond to Webhook](https://github.com/n8n-io/n8n/blob/master/packages/nodes-base/nodes/RespondToWebhook/RespondToWebhook.node.ts), and [Schedule Trigger](https://github.com/n8n-io/n8n/blob/master/packages/nodes-base/nodes/Schedule/ScheduleTrigger.node.ts). These source files were not copied into the project. Structural checks of an export are not a substitute for importing and executing it in the intended n8n version.
