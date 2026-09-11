# ADR 0020 — Attendance model

Status: Accepted for v0.4.0.

## Decision

La asistencia se registra contra `ClassSession`, no solamente contra una fecha.

Una ClassSession pertenece a:
- CourseOffering;
- Section;
- una fecha;
- un rango horario;
- opcionalmente un ScheduleSlot de origen.

Cada AttendanceRecord enlaza:
- ClassSession;
- StudentSectionAssignment;
- AttendanceCode;
- Section redundante para integridad relacional.

La combinación de FKs compuestas impide que una sesión de una sección registre un alumno
asignado a otra sección incluso si se intentara saltar la API.
