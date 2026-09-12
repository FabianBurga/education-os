from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import Counter
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import QueueHandler, QueueListener
from queue import Full, Queue
from uuid import uuid4

from app.core.config import settings

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_request_id: ContextVar[str | None] = ContextVar(
    "education_os_request_id",
    default=None,
)
_logger = logging.getLogger("education_os.runtime")
_logger.setLevel(logging.INFO)
_logger.propagate = False

_log_queue: Queue[logging.LogRecord] = Queue(maxsize=4096)
_log_drop_lock = threading.Lock()
_log_dropped_total = 0


def _increment_dropped_log() -> None:
    global _log_dropped_total
    with _log_drop_lock:
        _log_dropped_total += 1


def _dropped_log_count() -> int:
    with _log_drop_lock:
        return _log_dropped_total


class _DropSafeQueueHandler(QueueHandler):
    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except Full:
            _increment_dropped_log()


if not _logger.handlers:
    _stream_handler = logging.StreamHandler()
    _stream_handler.setFormatter(logging.Formatter("%(message)s"))
    _queue_handler = _DropSafeQueueHandler(_log_queue)
    _logger.addHandler(_queue_handler)
    _queue_listener = QueueListener(
        _log_queue,
        _stream_handler,
        respect_handler_level=True,
    )
    _queue_listener.start()


def current_request_id() -> str | None:
    return _request_id.get()


class RuntimeMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started = time.monotonic()
        self._requests: Counter[tuple[str, str]] = Counter()
        self._duration_sum = 0.0
        self._duration_max = 0.0
        self._inflight = 0

    def begin(self) -> None:
        with self._lock:
            self._inflight += 1

    def complete(
        self,
        *,
        method: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        status_class = f"{status_code // 100}xx"
        with self._lock:
            self._inflight = max(0, self._inflight - 1)
            self._requests[(method, status_class)] += 1
            self._duration_sum += duration_seconds
            self._duration_max = max(
                self._duration_max,
                duration_seconds,
            )

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "uptime_seconds": time.monotonic() - self._started,
                "requests": dict(self._requests),
                "duration_sum": self._duration_sum,
                "duration_max": self._duration_max,
                "inflight": self._inflight,
                "runtime_log_dropped_total": _dropped_log_count(),
            }

    def render_prometheus(self) -> str:
        snapshot = self.snapshot()
        lines = [
            "# HELP education_os_build_info Education OS runtime build metadata.",
            "# TYPE education_os_build_info gauge",
            (
                "education_os_build_info"
                f'{{milestone="M17",release="{settings.RELEASE_ID}"}} 1'
            ),
            "# HELP education_os_process_uptime_seconds Process uptime in seconds.",
            "# TYPE education_os_process_uptime_seconds gauge",
            (
                "education_os_process_uptime_seconds "
                f"{float(snapshot['uptime_seconds']):.6f}"
            ),
            "# HELP education_os_http_requests_inflight Current HTTP requests.",
            "# TYPE education_os_http_requests_inflight gauge",
            (
                "education_os_http_requests_inflight "
                f"{int(snapshot['inflight'])}"
            ),
            "# HELP education_os_http_requests_total HTTP requests by method and status class.",
            "# TYPE education_os_http_requests_total counter",
        ]

        requests = snapshot["requests"]
        assert isinstance(requests, dict)
        for (method, status_class), count in sorted(requests.items()):
            lines.append(
                "education_os_http_requests_total"
                f'{{method="{method}",status_class="{status_class}"}} {count}'
            )

        total_requests = sum(requests.values())
        lines.extend(
            [
                "# HELP education_os_http_request_duration_seconds_sum "
                "Total observed HTTP request duration.",
                "# TYPE education_os_http_request_duration_seconds_sum counter",
                (
                    "education_os_http_request_duration_seconds_sum "
                    f"{float(snapshot['duration_sum']):.6f}"
                ),
                "# HELP education_os_http_request_duration_seconds_count "
                "Number of observed HTTP request durations.",
                "# TYPE education_os_http_request_duration_seconds_count counter",
                (
                    "education_os_http_request_duration_seconds_count "
                    f"{total_requests}"
                ),
                "# HELP education_os_http_request_duration_seconds_max "
                "Maximum observed HTTP request duration since process start.",
                "# TYPE education_os_http_request_duration_seconds_max gauge",
                (
                    "education_os_http_request_duration_seconds_max "
                    f"{float(snapshot['duration_max']):.6f}"
                ),
                "# HELP education_os_runtime_log_dropped_total "
                "Structured runtime log records dropped because the async queue was full.",
                "# TYPE education_os_runtime_log_dropped_total counter",
                (
                    "education_os_runtime_log_dropped_total "
                    f"{int(snapshot['runtime_log_dropped_total'])}"
                ),
            ]
        )
        return "\n".join(lines) + "\n"


runtime_metrics = RuntimeMetrics()


def _header(scope: dict, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            try:
                return value.decode("latin-1")
            except UnicodeDecodeError:
                return None
    return None


def _safe_request_id(scope: dict) -> str:
    incoming = _header(scope, b"x-request-id")
    if incoming and _REQUEST_ID_RE.fullmatch(incoming):
        return incoming
    return uuid4().hex


def _route_template(scope: dict) -> str:
    route = scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return "UNMATCHED"


def _emit_runtime_log(
    *,
    request_id: str,
    method: str,
    route: str,
    status_code: int,
    duration_ms: float,
    error_type: str | None,
) -> None:
    payload: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": "http.request.completed",
        "request_id": request_id,
        "method": method,
        "route": route,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 3),
        "slow": duration_ms >= settings.SLOW_REQUEST_MS,
        "release": settings.RELEASE_ID,
        "environment": settings.APP_ENV,
    }
    if error_type:
        payload["error_type"] = error_type
    _logger.info(json.dumps(payload, separators=(",", ":"), sort_keys=True))


class RuntimeObservabilityMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = _safe_request_id(scope)
        context_token = _request_id.set(request_id)
        started = time.perf_counter()
        runtime_metrics.begin()
        status_code = 500
        error_type: str | None = None

        async def send_with_request_id(message):
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
                headers = list(message.get("headers", []))
                if not any(
                    key.lower() == b"x-request-id"
                    for key, _value in headers
                ):
                    headers.append(
                        (b"x-request-id", request_id.encode("ascii"))
                    )
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            duration = time.perf_counter() - started
            runtime_metrics.complete(
                method=str(scope.get("method", "UNKNOWN")).upper(),
                status_code=status_code,
                duration_seconds=duration,
            )
            _emit_runtime_log(
                request_id=request_id,
                method=str(scope.get("method", "UNKNOWN")).upper(),
                route=_route_template(scope),
                status_code=status_code,
                duration_ms=duration * 1000.0,
                error_type=error_type,
            )
            _request_id.reset(context_token)
