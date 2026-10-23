# Limitations (what the copilot cannot do, and what we do instead)

Source of truth: `backend/app/knowledge/limitations.yaml` (rendered in the UI as manual-step cards with a **Done** button that re-verifies).

## Liara API limits

| Limitation | Why | What the product does |
|---|---|---|
| Charging the account | `GET /v1/billing` is read-only; payment is console-only | Manual-step card with console link; after *Done* the balance and runway are re-checked and the wizard resumes |
| Creating / revoking API tokens | Not in the API | Setup instructions; token lives only in `.env` |
| Connecting GitHub/GitLab | API only lists integrations | Card pointing to console CI/CD; the copilot deploys from the local folder instead |
| Changing registrar / IRNIC nameservers | Outside Liara | Manual-step card with the exact nameservers, then `PUT zones/{zone}/check` polling |
| DNS records on an external DNS (e.g. Cloudflare) | Outside Liara | Card with the three records (ALIAS/CNAME, TXT, CNAME for SSL), Cloudflare proxy note, then `domains/{id}/check` polling |
| Alerts / webhooks | No such API | Polling watcher (20s default) with threshold, slope and z-score rules |
| Token scopes / least privilege | Tokens are full-access | Policy layer: tiers, app allowlist, cost guard, dry-run, guarded tools off by default |
| Executing commands inside the container | WebSocket exec sends the token in the query string | Deliberately unsupported in this version |
| Metric units & granularity | Undocumented | Marked ASSUMED; the probe prints raw samples; instant symptoms come from our own HTTP probe and logs |
| Rollback endpoint | None; rollback = re-release a previous source | Implemented as `redeploy_release` (needs `sourceID` in the release response — verified by the probe) |

## Product limits (this version)

- MVP targets PaaS apps (Node/Python/PHP/Go/Docker/static); databases are detected and reported but not provisioned.
- Deploy from the local folder (CLI or raw API). Git-based CI/CD is pointed to, not driven.
- The watcher runs while the backend runs (not a 24/7 service); that is acceptable for the challenge and shown as automation.
- Hypotheses are rule-based with optional LLM refinement; confidence is heuristic, not calibrated.
- Mock mode replays shapes from the official spec; field vocabularies marked ASSUMED may differ on the real API until probed.
- The web UI has a single shared password (`COPILOT_UI_PASSWORD`) for public deployments; there is no per-user auth or roles.
