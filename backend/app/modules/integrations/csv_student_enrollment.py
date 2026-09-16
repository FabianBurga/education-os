"""Bounded, fixed-schema CSV parsing for the M24-3 create-only workflow."""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status

MAX_FILE_BYTES = 1_000_000
MAX_ROWS = 1_000
MAX_COLUMNS = 9
MAX_CELL_LENGTH = 320
REQUIRED_COLUMNS = frozenset({
    "external_student_id", "given_names", "family_names", "academic_period_code", "campus_id",
})
OPTIONAL_COLUMNS = frozenset({"student_code", "enrollment_number", "enrollment_status", "enrolled_on"})
ALLOWED_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS


@dataclass(frozen=True, slots=True)
class CsvRow:
    row_number: int
    external_student_id: str
    given_names: str
    family_names: str
    academic_period_code: str
    campus_id: str
    student_code: str | None
    enrollment_number: str | None
    enrollment_status: str
    enrolled_on: date | None


def _error(code: str, detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": code, "message": detail})


def _value(raw: str | None, *, maximum: int, required: bool = False) -> str | None:
    value = (raw or "").strip()
    if required and not value:
        raise ValueError("required value is empty")
    if len(value) > maximum:
        raise ValueError("value exceeds maximum length")
    return value or None


def parse_csv_student_enrollment(payload: bytes) -> tuple[str, list[CsvRow]]:
    if not payload or len(payload) > MAX_FILE_BYTES:
        raise _error("CSV_TOO_LARGE", f"CSV must be between 1 and {MAX_FILE_BYTES} bytes")
    if b"\x00" in payload:
        raise _error("CSV_ENCODING_INVALID", "CSV must be UTF-8 text without NUL bytes")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _error("CSV_ENCODING_INVALID", "CSV must use UTF-8 encoding") from exc
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = reader.fieldnames
        if not headers or any(header is None for header in headers):
            raise _error("CSV_SCHEMA_INVALID", "CSV header is required")
        normalized_headers = [header.strip() for header in headers]
        if len(normalized_headers) > MAX_COLUMNS or len(set(normalized_headers)) != len(normalized_headers):
            raise _error("CSV_SCHEMA_INVALID", "CSV has duplicate or too many columns")
        if set(normalized_headers) != set(headers) or not REQUIRED_COLUMNS.issubset(normalized_headers):
            raise _error("CSV_SCHEMA_INVALID", "CSV required columns are missing")
        if not set(normalized_headers).issubset(ALLOWED_COLUMNS):
            raise _error("CSV_SCHEMA_INVALID", "CSV contains unsupported columns")
        rows: list[CsvRow] = []
        for row_number, row in enumerate(reader, start=2):
            if row_number - 1 > MAX_ROWS:
                raise _error("CSV_TOO_MANY_ROWS", f"CSV may contain at most {MAX_ROWS} data rows")
            if None in row:
                raise _error("CSV_ROW_INVALID", f"row {row_number} has too many values")
            for cell in row.values():
                if cell is not None and len(cell) > MAX_CELL_LENGTH:
                    raise _error("CSV_ROW_INVALID", f"row {row_number} contains an overlong cell")
            try:
                status_value = (_value(row.get("enrollment_status"), maximum=20) or "PENDING").upper()
                if status_value not in {"PENDING", "ACTIVE"}:
                    raise ValueError("enrollment_status must be PENDING or ACTIVE")
                enrolled_raw = _value(row.get("enrolled_on"), maximum=10)
                rows.append(CsvRow(
                    row_number=row_number,
                    external_student_id=_value(row.get("external_student_id"), maximum=120, required=True) or "",
                    given_names=_value(row.get("given_names"), maximum=160, required=True) or "",
                    family_names=_value(row.get("family_names"), maximum=160, required=True) or "",
                    academic_period_code=_value(row.get("academic_period_code"), maximum=40, required=True) or "",
                    campus_id=_value(row.get("campus_id"), maximum=36, required=True) or "",
                    student_code=_value(row.get("student_code"), maximum=64),
                    enrollment_number=_value(row.get("enrollment_number"), maximum=64),
                    enrollment_status=status_value,
                    enrolled_on=date.fromisoformat(enrolled_raw) if enrolled_raw else None,
                ))
            except (TypeError, ValueError) as exc:
                raise _error("CSV_ROW_INVALID", f"row {row_number} is invalid") from exc
    except csv.Error as exc:
        raise _error("CSV_SCHEMA_INVALID", "CSV is malformed") from exc
    return hashlib.sha256(payload).hexdigest(), rows
