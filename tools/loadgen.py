#!/usr/bin/env python3
"""Traffic generator for the demo: hits the sample app so faults become visible quickly.

python tools/loadgen.py --url https://shop-demo.liara.run --rps 5 --seconds 120
python tools/loadgen.py --url http://127.0.0.1:3000 --mix leak      # mostly /api/products
"""

from __future__ import annotations

import argparse
import asyncio
import random
import time

import httpx

MIXES = {
    "normal": [("/", 0.3), ("/api/products", 0.5), ("/health", 0.2)],
    "leak": [("/api/products", 0.9), ("/", 0.1)],
    "slow": [("/slow", 0.7), ("/api/products", 0.3)],
    "error": [("/api/checkout", 0.7), ("/api/products", 0.3)],
}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--rps", type=float, default=5)
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--mix", choices=MIXES, default="normal")
    args = parser.parse_args()
    paths, weights = zip(*MIXES[args.mix], strict=True)
    stats = {"ok": 0, "err": 0, "latencies": []}
    deadline = time.time() + args.seconds
    async with httpx.AsyncClient(base_url=args.url.rstrip("/"), timeout=10) as http:
        while time.time() < deadline:
            path = random.choices(paths, weights)[0]
            started = time.perf_counter()
            try:
                if path == "/api/checkout":
                    r = await http.post(
                        path, json={"items": [{"id": random.choice([1, 2, 99]), "qty": 1}]}
                    )
                else:
                    r = await http.get(path)
                stats["ok" if r.status_code < 500 else "err"] += 1
            except httpx.HTTPError:
                stats["err"] += 1
            stats["latencies"].append((time.perf_counter() - started) * 1000)
            if (stats["ok"] + stats["err"]) % 25 == 0:
                lat = sorted(stats["latencies"])[-50:]
                print(
                    f"sent={stats['ok'] + stats['err']} ok={stats['ok']} err={stats['err']} p50={sorted(lat)[len(lat) // 2]:.0f}ms",
                    flush=True,
                )
            await asyncio.sleep(max(0.0, 1 / args.rps - (time.perf_counter() - started)))
    print("done", {k: v for k, v in stats.items() if k != "latencies"})


if __name__ == "__main__":
    asyncio.run(main())
