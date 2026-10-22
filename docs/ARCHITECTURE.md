# Architecture

Short version in the README. This page is the engineering reference.

## 1. Principles

1. **The LLM proposes; deterministic code executes, verifies and enforces policy.** No side effect ever originates from model text; the model can only call registered tools, and T2+ tools create *proposals*.
2. **Proposal → Approval → Execute → Verify → Audit** for every state change (web UI, CLI and MCP share one `ProposalService`).
3. **Evidence first.** Diagnoses cite numbers and log lines, carry a confidence, and say what would change the conclusion.
4. **Local-first.** Needs the user's project folder and (for live deploys) the Liara CLI.
5. **Honest about limits.** `limitations.yaml` is a first-class registry rendered as manual-step cards.
6. **Works without an LLM.** Routing, wizards, analyzers and remediation are rule-based; the LLM adds free-form chat, plain-Persian explanations and hypothesis re-ranking.

## 2. Components

| Module | Responsibility |
|---|---|
| `app/liara/client.py` | Typed async client: auth, `teamID`, throttle, retries, circuit breaker, error normalisation, fixture recorder |
| `app/liara/models.py` | Pydantic views of responses, each field tagged VERIFIED / ASSUMED |
| `app/liara/redaction.py` | Masks JWTs, bearer tokens, URL credentials, `*_KEY/SECRET/TOKEN` env values |
| `app/policy/tiers.py` | Tool registry: tier, cost impact, reversibility, downtime, verification definition |
| `app/policy/engine.py` | `decide()` (auto / notice / approval / blocked), HMAC single-use approval tokens, idempotency keys |
| `app/policy/proposals.py` | Proposal lifecycle + executors/verifiers + audit + timeline events |
| `app/store/db.py` | SQLite: sessions, timeline, proposals, audit (append-only), incidents, metric snapshots ring, human tokens, secret |
| `app/deploy/analyzer.py` | Platform (mirrors CLI detection), port, env keys, DB needs, health path |
| `app/deploy/advisor.py` | Plan options from the live catalog, hourly/monthly cost, runway, recommendation |
| `app/deploy/engine.py` | `liara deploy` runner (stream + mask) with raw API fallback (sources + releases), rollback by re-release |
| `app/deploy/verifier.py` | Release polling, applet state, HTTP probe series, error-burst check |
| `app/deploy/wizard.py` | Deploy state machine (analyze → advise → balance → env → proposal → stepper → verify) |
| `app/sre/collectors.py` | Parallel gather of project, plan, logs, events, cpu/memory, releases, applets, HTTP probe |
| `app/sre/analyzers.py` | Pure functions: saturation, memory trend (slope + monotonicity on recent window), restarts/OOM, error bursts + log clustering + stack extraction, latency regression, release correlation |
| `app/sre/evidence.py` | Compact redacted EvidenceBundle |
| `app/sre/hypotheses.py` | Rule ranking (needs/boost sets) + optional LLM re-ranking constrained to the same ids |
| `app/sre/remediation.py` | Options with risk/cost/reversibility mapped to policy tools (rollback, restart, resize, config fix, code fix) |
| `app/sre/verifier.py` | Post-remediation re-probe rounds, before/after comparison |
| `app/sre/investigator.py` | Orchestrates the read-only pipeline and persists the incident |
| `app/watcher/scheduler.py` | asyncio poller → snapshots ring → threshold/slope/z-score rules → opens incident + auto-investigation |
| `app/bridge/fix_brief.py` | FixBrief builder, command-runner adapter, `git apply` patching, demo-patch mode |
| `app/llm/gateway.py` | OpenAI-compatible client (BoxAPI), strong/small routing, native tools or JSON action protocol, structured outputs with repair, embeddings, token accounting |
| `app/agent/loop.py` | Keyword router → LLM router → tool loop; dispatch to wizards/investigator/proposals |
| `app/api/routes.py` | REST + SSE for the UI; `app/mcp_server.py` MCP tools; `app/cli.py` Typer CLI |
| `app/knowledge/` | `limitations.yaml` registry; RAG over Liara docs (embeddings or keyword fallback) |

## 3. Core flows

**Deploy.** `ProjectAnalyzer` → `PlanAdvisor` (catalog from `/v1/me`, balance from `/v1/billing`) → if balance low: manual-step card *charge account* (blocking when runway < 1h) → env form for discovered keys → one `deploy_project` proposal (create app if missing, set envs, write `liara.json`, deploy) → live stepper events → `DeployVerifier` (release READY → applet running → HTTP 200 ×3 → no error burst) → success card → watcher starts.

**Operate.** restart / scale / set_env / resize / add_domain are proposals with impact (cost delta per hour and month, reversibility, downtime, rollback plan). Each has a verifier (health after settle; plan applied + metrics vs baseline; domain status + certificates + HTTPS). Status questions are T0 and answered immediately.

**Incident.** Triggered by the watcher or by the user ("site is slow"). `Investigator` streams: collecting → analyzing → evidence → hypotheses → remediation. The human picks an option (it becomes a proposal), approves, the executor runs, the verifier re-probes and compares. `fix-brief` + `run-coding-agent` produce a patch (CODING_AGENT_CMD or the deterministic demo patch) that is applied only through a `submit_fix` proposal (diff shown first).

**Verification definitions** (`policy/tiers.py: verification`): deploy = release READY ∧ applet running ∧ HTTP 200 on health path ∧ no error burst; restart = applet restarted ∧ health OK; env = health OK ∧ clean logs; resize = plan applied ∧ metrics compared to baseline; domain = check status SET ∧ certificates OK ∧ HTTPS 200.

## 4. Risk tiers

| Tier | Examples | Behaviour |
|---|---|---|
| T0 | reads, analyze, investigate | automatic |
| T1 | DNS re-check, health loop, watch toggle | automatic with a visible notice + audit |
| T2 | create app, deploy, restart, scale, env, resize, domain, ssl, settings, submit fix | proposal card, human approval, execute, verify, audit |
| T3 | delete app/domain, ssl disable, downgrade | disabled unless `COPILOT_ENABLE_GUARDED=true`, typed confirmation |

Extra guards: app allowlist, cost guard (max added Toman/hour), dry-run, idempotency key per proposal, single-use HMAC approval tokens stored only in the local DB (never returned through MCP), append-only audit.

## 5. Liara API facts

Legend: **V** = VERIFIED in the official OpenAPI (`developers.liara.ir/spec/*.yaml`) or CLI source (`liara-cloud/cli` v9.6.0); **A** = ASSUMED, confirm with `tools/probe.py`.

- Hosts: PaaS/account/billing on `https://api.liara.ir` (V; `api.iran.liara.ir` also exists in the CLI constants); DNS on `https://dns-service.liara.ir` (V).
- Auth header `Authorization: Bearer <JWT>` (V). Team: `?teamID=` on every request (V, CLI `base.ts`).
- `/v1/me`: `user`, optional `team`, `plans.projects[planID] = {available, region, RAM.amount, CPU.amount, volume, price, storageClass}`; monthly = hourly × 720 (V, CLI `app/create.ts`).
- `/v1/billing` → `{user: {balance, accountType, minCreditAmount}}` (V).
- Projects list fields: `_id, project_id, type, status, scale, planID, created_at, isDeployed` (V); details add `envs[{key,value,encrypted}], hourlyPrice, zeroDowntime, defaultSubdomain, readOnlyRootFilesystem, fixedIPStatus` (V).
- Deploy: `POST /v2/projects/{name}/sources` multipart `file` (tar.gz) → `{sourceID}`; `POST /v2/projects/{name}/releases {sourceID, port, type}` → `{releaseID}`; `GET /v1/releases/{id}` → `{release:{state, queue, ...}}` with states BUILDING/PUSHING/PUSHED/DEPLOYING/UNHEALTHY/FAILED/READY (V, CLI `deploy.ts`). Whether a previous release's `sourceID` is returned by the API (needed for rollback by re-release) is **A**.
- Logs: `GET .../logs?since=` returns `[{type, datetime, message}]` (V); `since` format **A** (unix seconds tried first, probe tests alternatives).
- Metrics: `GET .../metrics/{cpu,memory,network-*}?since=` → `{end, result:[{applet, values:[[ts, "value"]]}]}` (V); units **A** (cpu cores, memory bytes), granularity **A**. `metrics/summary` → `{cpuUsage[{value:[ts,v], applet}], memoryUsage, disksUsage}` (V).
- Events: `GET .../events?search&start&end` → `{data:[{metaData, values:[[ts,text]]}]}` (V).
- Applets: `{applets:[{id,name,timestamp,state,reason,release:{releaseID,tag}}]}` (V); `state`/`reason` vocab **A** (Running / Waiting / CrashLoopBackOff / OOMKilled assumed k8s-like).
- Domains: create `{name, project, type:"PROJECT"}` → `{domain:{_id}}`; check → `{domain:{status, certificatesStatus, CNameRecord, verificationCode}}` (V); status vocab **A** (`SET`, `OK` assumed).
- Default subdomain `https://<app>.liara.run` **A** (user docs); override with `DEMO_APP_URL` for the probe.
- Error bodies: `{message}` assumed (A). Rate limits: documented as existing, no numbers → client-side throttle + backoff.
- No alert/webhook API (V, absent from spec) → polling watcher. Token scopes: none (V) → policy layer.

## 6. Storage

SQLite (`backend/data/copilot.sqlite`): `sessions`, `timeline` (event stream per session), `proposals`, `audit` (append-only), `incidents`, `snapshots` (per-app ring buffer, 720 samples), `human_tokens`, `meta` (HMAC secret). Vector index for docs in `app/knowledge/docs/.index.npz`. Secrets only from the environment.

## 7. Safety against prompt injection

Logs, docs and tool outputs are fenced as untrusted data in prompts; the model's tool surface is constrained per mode (investigation is read-only); env values, tokens and connection strings are masked before anything reaches the LLM; no token ever appears in a URL; timeouts and a circuit breaker protect against repeated API failures.

## 8. Testing

`backend/tests`: policy + approval lifecycle (replay, single-use, model cannot run T2), redaction, analyzers on synthetic series, project analyzer on real folders, deploy advisor, and API end-to-end against the in-process mock (status/restart/verify, memory-leak investigation + fix brief, deploy wizard creating an app). `tools/mock_liara` replays VERIFIED shapes and scripts faults (`memory_leak`, `cpu_saturation`, `error_burst`, `bad_release`). Opt-in contract checks run read-only against the real API via `tools/probe.py`.
