from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import psycopg

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from tools.acceptance.harness import (  # noqa: E402
    edge_path,
    http,
    start_uvicorn,
    stop_process,
)

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@localhost:5432/education_os",
)


def _assert_database_revision() -> None:
    with psycopg.connect(OWNER_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        row = cur.fetchone()
        assert row == ("0016_m14",), row
    print("M17 database revision 0016_m14 unchanged: PASSED")


def _assert_runtime_endpoints(base_url: str) -> None:
    status, legacy, headers = http(base_url, "/health")
    assert status == 200 and legacy == {
        "status": "ok",
        "milestone": "M15",
    }
    assert headers.get("x-request-id")
    print("M17 legacy health compatibility: PASSED")

    status, live, headers = http(base_url, "/health/live")
    assert status == 200 and isinstance(live, dict)
    assert live["status"] == "alive"
    assert live["milestone"] == "M17"
    assert live["release"] == "v1.0.0-rc7"
    assert headers.get("x-request-id")
    print("M17 liveness endpoint: PASSED")

    custom_request_id = "m17-verifier-request-001"
    status, ready, headers = http(
        base_url,
        "/health/ready",
        headers={"X-Request-ID": custom_request_id},
    )
    assert status == 200 and isinstance(ready, dict), ready
    assert ready["status"] == "ready"
    assert ready["milestone"] == "M17"
    assert ready["checks"]["database"] == "ok"
    assert headers.get("x-request-id") == custom_request_id
    print("M17 readiness + request correlation: PASSED")

    status, _missing, invalid_headers = http(
        base_url,
        "/this-path-must-not-exist/123456789",
        headers={"X-Request-ID": "bad request id with spaces"},
    )
    assert status == 404
    replacement = invalid_headers.get("x-request-id")
    assert replacement
    assert replacement != "bad request id with spaces"

    status, metrics, headers = http(base_url, "/metrics")
    assert status == 200 and isinstance(metrics, str)
    assert headers.get("x-request-id")
    required_metrics = (
        'education_os_build_info{milestone="M17",release="v1.0.0-rc7"} 1',
        "education_os_http_requests_total",
        'status_class="2xx"',
        'status_class="4xx"',
        "education_os_http_request_duration_seconds_sum",
        "education_os_http_requests_inflight",
    )
    for expected in required_metrics:
        assert expected in metrics, expected
    print("M17 privacy-minimized runtime metrics: PASSED")


def _assert_real_edge(base_url: str, evidence_dir: Path) -> None:
    from playwright.sync_api import sync_playwright

    evidence_dir.mkdir(parents=True, exist_ok=True)
    screenshot = evidence_dir / "m17_runtime_foundation_edge.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=edge_path(),
            headless=True,
        )
        page = browser.new_page(
            viewport={"width": 1500, "height": 1050},
        )

        response = page.goto(
            f"{base_url}/app/",
            wait_until="domcontentloaded",
        )
        assert response is not None
        assert response.status == 200
        request_id = response.headers.get("x-request-id")
        assert request_id

        page.get_by_test_id("unified-token-input").wait_for(timeout=15000)
        page.screenshot(path=str(screenshot), full_page=True)
        browser.close()

    assert screenshot.is_file()
    assert screenshot.stat().st_size > 0
    print(f"M17 browser screenshot={screenshot}")
    print("M17 real Microsoft Edge runtime acceptance: PASSED")


def _assert_structured_logs(output: str) -> None:
    payloads: list[dict[str, object]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        if '"event":"http.request.completed"' not in line:
            continue
        payload = json.loads(line)
        payloads.append(payload)

    assert payloads, "No M17 structured request logs captured"
    routes = {str(payload["route"]) for payload in payloads}
    assert "/health/live" in routes
    assert "/health/ready" in routes
    assert "/metrics" in routes
    assert "UNMATCHED" in routes

    for payload in payloads:
        assert payload["release"] == "v1.0.0-rc7"
        assert payload["request_id"]
        assert "authorization" not in json.dumps(payload).lower()
        route = str(payload["route"])
        assert "123456789" not in route

    print("M17 structured privacy-minimized request logging: PASSED")


def main() -> None:
    _assert_database_revision()

    evidence_dir = Path(
        os.getenv(
            "M17_EVIDENCE_DIR",
            str(
                Path.home()
                / "Downloads"
                / "Education_OS_M17_Evidence"
            ),
        )
    )

    process, base_url = start_uvicorn(BACKEND_ROOT)
    print(f"M17 actual HTTP server READY at {base_url}")
    output = ""
    try:
        _assert_runtime_endpoints(base_url)
        _assert_real_edge(base_url, evidence_dir)
    finally:
        # M17 request logging is intentionally asynchronous so legacy verifier
        # subprocess pipes can never block HTTP responses. Give the queue a
        # brief drain window before terminating this acceptance server.
        time.sleep(0.25)
        output = stop_process(process)

    _assert_structured_logs(output)

    report = {
        "milestone": "M17",
        "release_candidate": "v1.0.0-rc7",
        "database_revision": "0016_m14",
        "checks": {
            "legacy_health_compatibility": "PASS",
            "liveness": "PASS",
            "readiness": "PASS",
            "request_correlation": "PASS",
            "runtime_metrics": "PASS",
            "structured_logging": "PASS",
            "real_edge": "PASS",
        },
        "result": "PASS",
    }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report_path = evidence_dir / "m17_reliability_foundation.json"
    report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"M17 reliability report={report_path}")
    print("M17 PRODUCTION RELIABILITY FOUNDATION v1.0.0-rc7: PASSED")


if __name__ == "__main__":
    main()
