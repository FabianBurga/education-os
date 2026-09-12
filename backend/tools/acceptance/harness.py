from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http(
    base_url: str,
    path: str,
    *,
    token: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, object, dict[str, str]]:
    request_headers = {"Accept": "application/json"}
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(
        f"{base_url}{path}",
        headers=request_headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            content_type = response.headers.get("content-type", "")
            body: object = raw
            if "application/json" in content_type:
                body = json.loads(raw)
            return (
                response.status,
                body,
                {key.lower(): value for key, value in response.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        return (
            exc.code,
            body,
            {key.lower(): value for key, value in exc.headers.items()},
        )


def wait_for_health(
    base_url: str,
    process: subprocess.Popen,
    *,
    path: str = "/health/live",
    timeout_seconds: int = 30,
) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        if process.poll() is not None:
            output = ""
            if process.stdout is not None:
                output = process.stdout.read()
            raise RuntimeError(
                f"uvicorn exited early with code {process.returncode}: {output}"
            )
        try:
            status, body, _headers = http(base_url, path)
            if status == 200:
                return
            last_error = f"{status}: {body}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"HTTP server not ready: {last_error}")


def start_uvicorn(
    backend_root: Path,
    *,
    env: dict[str, str] | None = None,
) -> tuple[subprocess.Popen, str]:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "info",
        ],
        cwd=str(backend_root),
        env=process_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    wait_for_health(base_url, process)
    return process, base_url


def stop_process(process: subprocess.Popen) -> str:
    if process.poll() is None:
        process.terminate()
    try:
        output, _unused = process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _unused = process.communicate(timeout=5)
    return output or ""


def edge_path() -> str:
    candidates = (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("Microsoft Edge executable not found")
