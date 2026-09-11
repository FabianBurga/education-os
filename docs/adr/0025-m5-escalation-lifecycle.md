# ADR 0025 — Task acknowledgement, completion and escalation

Status: Accepted for v0.6.0.

## Lifecycle

OPEN → ACKNOWLEDGED → COMPLETED

Si OPEN/ACKNOWLEDGED supera su `escalate_at`:

OPEN|ACKNOWLEDGED → ESCALATED

Una tarea escalada todavía requiere intervención humana para cerrarse.

Cada transición genera AutomationTimelineEvent.
