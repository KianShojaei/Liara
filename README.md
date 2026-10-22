# Liara Ops Copilot

> دستیار فنیِ صاحب سایت برای لیارا: راه‌اندازی و دیپلوی، عملیات روزمره، پایش و عیب‌یابی هوشمند (SRE) — همیشه با تأیید انسان برای کارهای حساس.

**تصور کنید یک برنامه‌نویس یک سایت ساخته و از دیپلوی چیزی نمی‌داند.** به کوپایلوت می‌گوید «این پروژه را دیپلوی کن»؛ کوپایلوت پوشه را بررسی می‌کند، پلن مناسب را با هزینه‌ی ساعتی و «زمان باقی‌مانده‌ی موجودی» پیشنهاد می‌دهد، یک کارت تأیید نشان می‌دهد و بعد از تأیید، برنامه را می‌سازد، دیپلوی می‌کند و سلامتش را تأیید می‌کند. اگر بعداً سایت کند شود، Watcher خودش متوجه می‌شود، لاگ‌ها و متریک‌ها را تحلیل می‌کند، علت‌های محتمل را با درصد اطمینان رتبه‌بندی می‌کند، راه‌حل‌ها را با ریسک و هزینه پیشنهاد می‌دهد، و در صورت تأیید، اجرا و نتیجه را بررسی می‌کند. برای رفع ریشه‌ای، یک FixBrief به ایجنت کدنویسی (Claude Code، Cursor…) می‌دهد.

```
پیشنهاد (LLM/قوانین)  →  تأیید انسان  →  اجرا (کد قطعی)  →  بررسی نتیجه  →  ثبت در audit
```

## فهرست

- [معماری در یک نگاه](#معماری-در-یک-نگاه) · جزئیات: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [اتصال به API های لیارا](#اتصال-به-api-های-لیارا)
- [محدودیت‌ها](#محدودیتها) · کامل: [docs/LIMITATIONS.md](docs/LIMITATIONS.md)
- [نحوه‌ی تعامل کاربر](#نحوهی-تعامل-کاربر)
- [اجرا](#اجرا) · [سناریوی دمو](docs/DEMO_SCRIPT.md)
- [امنیت و سیاست‌ها](#امنیت-و-سیاستها)

## معماری در یک نگاه

```
┌───────────── Interfaces ─────────────┐      ┌──────────── Orchestrator (FastAPI) ────────────┐
│ Web UI (React, RTL, SSE)             │      │ Agent loop: keyword router → LLM router →       │
│ CLI  (copilot ...)                   │◄────►│   tool-calling loop (T0 auto, T2 → proposal)    │
│ MCP server (stdio / streamable-http) │      │ Deterministic state machines: DeployWizard,     │
└──────────────────────────────────────┘      │   Investigator, Watcher                         │
                                              └───────┬──────────────┬─────────────┬───────────┘
            ┌─────────────────────────────────────────┤              │             │
            ▼                                         ▼              ▼             ▼
┌────────────────────┐  ┌───────────────────────┐  ┌──────────┐  ┌──────────────────┐
│ Policy engine      │  │ Capability modules    │  │ LLM gw   │  │ Store (SQLite)   │
│ T0/T1/T2/T3 tiers  │  │ LiaraClient (httpx)   │  │ BoxAPI   │  │ timeline,        │
│ allowlist, cost    │  │ ProjectAnalyzer/Advisor│ │ OpenAI-  │  │ proposals, audit,│
│ guard, dry-run,    │  │ DeployEngine (CLI/API)│  │ compat.  │  │ incidents,       │
│ signed single-use  │  │ SRE: collectors →     │  │ strong + │  │ snapshots ring   │
│ approvals, audit   │  │  analyzers → evidence │  │ small    │  └──────────────────┘
└────────────────────┘  │  → hypotheses →       │  │ models,  │
                        │  remediation → verify │  │ JSON     │  ┌──────────────────┐
                        │ CodingAgentBridge     │  │ fallback │  │ Knowledge: RAG + │
                        │ Watcher (poll + rules)│  └──────────┘  │ limitations.yaml │
                        └───────────────────────┘                └──────────────────┘
                                   │
                                   ▼
                     Liara API (api.liara.ir, dns-service.liara.ir)  /  tools/mock_liara
```

اصول: **LLM پیشنهاد می‌دهد، کدِ قطعی اجرا و تأیید می‌کند.** هر تغییر وضعیت از مسیر Proposal → Approval → Execute → Verify → Audit می‌گذرد. تشخیص مشکل «شواهدمحور» است (اعداد و خطوط لاگ، درصد اطمینان، و «چه چیزی نظرم را عوض می‌کند»). بدون کلید LLM هم همه‌ی جریان‌ها (دیپلوی، پایش، عیب‌یابی، تأیید) کار می‌کنند؛ LLM فقط توضیح و مسیردهی آزاد را بهتر می‌کند.

## اتصال به API های لیارا

| چه چیزی | چطور | وضعیت |
|---|---|---|
| احراز هویت | `Authorization: Bearer <JWT>` (توکن از کنسول → API) | VERIFIED |
| تیم | query param `teamID` روی همه‌ی درخواست‌ها (همان روش CLI رسمی) | VERIFIED |
| حساب و کاتالوگ پلن | `GET /v1/me` → `plans.projects[planID]` = `{available, region, RAM.amount, CPU.amount, volume, price(ساعتی), storageClass}` | VERIFIED (CLI) |
| موجودی | `GET /v1/billing` → `user.balance` | VERIFIED |
| برنامه‌ها | `GET/POST /v1/projects`, `GET /v1/projects/{name}` | VERIFIED |
| اجرا/توقف/ری‌استارت | `POST .../actions/scale {scale:0|1}`, `POST .../actions/restart` | VERIFIED |
| تغییر پلن | `POST /v1/projects/{name}/resize {planID}` | VERIFIED |
| متغیرهای محیطی | `POST /v1/projects/update-envs {project, variables[]}` | VERIFIED |
| دیپلوی | ترجیحاً `liara deploy --app --port --platform --path --api-token`; fallback: `POST /v2/projects/{name}/sources` (tar.gz) + `POST /v2/projects/{name}/releases {sourceID, port, type}` | VERIFIED |
| وضعیت release | `GET /v1/releases/{id}` → `READY/BUILDING/DEPLOYING/UNHEALTHY/FAILED` | VERIFIED (CLI) |
| مشاهده‌پذیری | `GET .../logs?since=`, `.../events`, `.../applets`, `.../releases`, `.../metrics/{summary,cpu,memory,...}?since=` | VERIFIED shape · واحد و granularity **ASSUMED** |
| دامنه | `GET /v1/domains?project=`, `POST /v1/domains`, `GET /v1/domains/{id}/check`, `POST /v1/domains/provision-ssl-certs` | VERIFIED |
| DNS | `dns-service.liara.ir/api/v1/zones`, `PUT zones/{zone}/check`, رکوردها | VERIFIED |

کلاینت (`backend/app/liara/client.py`): throttle سمت کلاینت، retry با backoff نمایی روی 429/5xx، circuit breaker، نرمال‌سازی خطا با پیام فارسی، ماسک کردن توکن و مقادیر حساس قبل از لاگ/LLM، و ضبط fixture برای mock. **همه‌ی فرضیات با `TODO(verify)`/ASSUMED علامت خورده‌اند و `tools/probe.py` آن‌ها را روی حساب واقعی چک می‌کند.** جزئیات: [docs/ARCHITECTURE.md §API facts](docs/ARCHITECTURE.md#liara-api-facts).

## محدودیت‌ها

API لیارا **نمی‌تواند**: حساب را شارژ کند، توکن بسازد، GitHub/GitLab را وصل کند، نیم‌سرور دامنه را نزد ثبت‌کننده عوض کند، هشدار/webhook بدهد، یا دسترسی توکن را محدود کند. در محصول هر کدام یک **کارت مرحله‌ی دستی** با دستور دقیق و دکمه‌ی «انجام شد» است که بعد از آن دوباره بررسی می‌کنیم. فهرست کامل و راه‌حل هر مورد: [docs/LIMITATIONS.md](docs/LIMITATIONS.md) (منبع: `backend/app/knowledge/limitations.yaml`).

## نحوه‌ی تعامل کاربر

1. **گفتگو به زبان ساده**: «دیپلوی ./my-site»، «وضعیت shop-demo»، «سایت کند شده»، «ری‌استارت»، «FAULT_MODE=none»، «ارتقا به ir-medium»، «دامنه shop.example.ir».
2. **کارت‌ها به‌جای متن خام**: تحلیل پروژه، گزینه‌های پلن با هزینه و زمان باقی‌مانده، فرم متغیرها، **کارت تأیید** (اثر هزینه، برگشت‌پذیری، downtime، برنامه‌ی بازگشت)، stepper زنده‌ی دیپلوی، کارت نتیجه‌ی بررسی، کارت شواهد (نمودار حافظه/CPU + یافته‌ها)، کارت فرضیه‌ها با نوار اطمینان، کارت راه‌حل‌ها با ریسک/هزینه، کارت مراحل دستی.
3. **پنل وضعیت زنده**: موجودی و runway، لیست برنامه‌ها با نقطه‌ی سلامت، sparkline حافظه/CPU، Watcher.
4. **سطوح ریسک**: T0 خواندن (خودکار) · T1 نوشتن کم‌ریسک (خودکار با اعلان) · T2 نیازمند تأیید (deploy, restart, scale, env, resize, domain) · T3 محافظت‌شده (delete, ssl disable, downgrade؛ پیش‌فرض خاموش + تأیید تایپی).
5. **همان ابزارها از CLI و MCP**: `copilot deploy ./site`، یا از داخل Claude Code/Cursor با MCP (`get_incident`, `get_fix_brief`, `submit_fix_result`). ابزارهای تغییردهنده در MCP فقط `pending_approval` برمی‌گردانند؛ تأیید فقط در UI/CLI انسانی است.

## اجرا

پیش‌نیاز: Python 3.11+، Node 18+، (برای دیپلوی واقعی) `npm i -g @liara/cli`.

```bash
cp .env.example .env            # LIARA_API_TOKEN, BOXAPI_API_KEY (اختیاری)، COPILOT_MODE=mock|live
make setup                      # venv + npm install (backend, frontend, demo)
make dev-up                     # mock Liara :8081 + demo app :3000 + backend :8000
make frontend                   # http://localhost:5173
```

- **ویندوز**: `make` ندارید؛ به‌جای آن `cd backend; uv venv .venv; uv pip install -p .venv\Scripts\python.exe -e ".[dev]"` و سپس از ریشه‌ی مخزن `.\scripts\dev_up.ps1` (هر سرویس در یک پنجره باز می‌شود). پایتون venv در ویندوز `backend\.venv\Scripts\python.exe` است.
- **حالت mock** (پیش‌فرض): بدون نیاز به توکن؛ `tools/mock_liara` شکل واقعی پاسخ‌ها را از OpenAPI رسمی بازپخش می‌کند و سناریوی خطا دارد:
  `curl -X POST localhost:8081/__mock/scenario -d '{"app":"shop-demo","scenario":"memory_leak","minutes_ago":4}' -H 'content-type: application/json'`
- **حالت live**: `COPILOT_MODE=live` و توکن در `.env`. اول `python tools/probe.py` را اجرا کنید (فقط GET، خروجی ماسک‌شده) تا فرضیات را تأیید کند. `COPILOT_APP_ALLOWLIST=shop-demo` دسترسی ایجنت را به همان برنامه محدود می‌کند؛ `COPILOT_DRY_RUN=true` اجرا را شبیه‌سازی می‌کند.
- **LLM**: `BOXAPI_API_KEY` و `python tools/llm_bench.py` برای انتخاب مدل قوی/کوچک و پروتکل (`tools` یا `json`).
- **MCP**: `claude mcp add liara-ops -- backend/.venv/bin/python -m app.mcp_server` (از پوشه‌ی backend).
- تست: `make test` (18 تست: policy، approvals، analyzers، analyzer پروژه، API end-to-end روی mock) · lint: `make lint`.

## امنیت و سیاست‌ها

- توکن‌ها فقط از `.env` خوانده می‌شوند؛ هرگز در URL، لاگ، timeline یا پرامپت LLM ظاهر نمی‌شوند (`redaction.py`). endpoint وب‌سوکت exec که توکن را در query می‌فرستد عمداً استفاده نشده.
- تأییدها توکن HMAC امضاشده و **یک‌بارمصرف** و متصل به شناسه‌ی proposal هستند؛ از مسیر MCP/مدل قابل دسترسی نیستند.
- allowlist برنامه، cost guard (سقف افزایش هزینه‌ی ساعتی)، dry-run، کلید idempotency، audit log فقط‌افزودنی (SQLite).
- خروجی ابزارها (لاگ، مستندات) برای LLM «داده‌ی غیرقابل‌اعتماد» است (دفاع در برابر prompt injection).

## ساختار مخزن

```
backend/app/   api/ agent/ policy/ liara/ deploy/ sre/ watcher/ bridge/ knowledge/ llm/ store/ mcp_server.py cli.py
frontend/      React + Vite + Tailwind (RTL)
tools/         probe.py  llm_bench.py  loadgen.py  mock_liara/
demo/shop-demo Express sample app with FAULT_MODE toggles + deterministic fix patch
docs/          ARCHITECTURE.md  LIMITATIONS.md  DEMO_SCRIPT.md
```
