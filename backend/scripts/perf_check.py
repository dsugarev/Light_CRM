"""NFR-01 performance check: p95 of list and search endpoints against a running stack.

    PERF_EMAIL=… PERF_PASSWORD=… uv run python scripts/perf_check.py [https://localhost]

Signs in once, calls each endpoint `ROUNDS` times in sequence (after one warm-up
call) and prints p50, p95 and max in milliseconds as a Markdown table. Exits with 1
when any p95 exceeds the 500 ms target. Run it after `python -m app.cli seed-demo`
so the NFR-01 volumes are present. Not part of CI: timings depend on the machine.
"""

import os
import statistics
import sys
import time

import httpx

TARGET_MS = 500.0
ROUNDS = 40
ENDPOINTS = (
    "/api/v1/organizations",
    "/api/v1/organizations?q=alfa%20mrezhi&sort=name",
    "/api/v1/organizations?city=Варна&sort=-created_at&page=20",
    "/api/v1/contacts?q=иванова",
    "/api/v1/leads",
    "/api/v1/leads?q=fibre&status=new&sort=-estimated_value",
    "/api/v1/leads?page=400",
    "/api/v1/opportunities",
    "/api/v1/opportunities?q=cloud&stage_type=open&sort=amount",
    "/api/v1/opportunities?is_stale=true",
    "/api/v1/opportunities/board",
    "/api/v1/activities",
    "/api/v1/search?q=vega",
    "/api/v1/search?q=Сириус",
    "/api/v1/reports/dashboard",
)


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "https://localhost"
    email, password = os.environ["PERF_EMAIL"], os.environ["PERF_PASSWORD"]
    headers = {"X-Requested-With": "XMLHttpRequest"}
    with httpx.Client(base_url=base, verify=False, headers=headers, timeout=30) as client:  # noqa: S501 - local self-signed certificate
        signed_in = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        signed_in.raise_for_status()
        failed = False
        sys.stdout.write("| Endpoint | p50 ms | p95 ms | max ms |\n|---|---|---|---|\n")
        for path in ENDPOINTS:
            client.get(path).raise_for_status()  # warm-up
            timings = []
            for _ in range(ROUNDS):
                start = time.perf_counter()
                client.get(path).raise_for_status()
                timings.append((time.perf_counter() - start) * 1000)
            p95 = statistics.quantiles(timings, n=20)[18]
            failed |= p95 > TARGET_MS
            median = statistics.median(timings)
            sys.stdout.write(f"| `{path}` | {median:.0f} | {p95:.0f} | {max(timings):.0f} |\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
