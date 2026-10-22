# shop-demo

Tiny Express API used as the sample app for Liara Ops Copilot.

Routes: `/`, `/health`, `/api/products`, `/api/checkout`, `/slow`.

Fault toggles via env `FAULT_MODE`:

| value   | effect                                                              |
|---------|---------------------------------------------------------------------|
| `none`  | healthy                                                             |
| `leak`  | `/api/products` keeps 1 MB per request forever (memory leak)        |
| `slow`  | `/slow` burns 1.5 s of CPU per request (CPU saturation)             |
| `error` | `/api/checkout` throws on unknown product ids (500 burst + stack)   |

`patches/fix-memory-leak.patch` is the deterministic patch used by the demo's
coding-agent bridge so the demo never depends on a live agent.

```bash
npm install && FAULT_MODE=leak npm start
```
