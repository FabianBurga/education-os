# ADR 0024 — Automation Engine

Status: Accepted for v0.6.0.

## Decision

M5 implementa automatización basada en reglas explícitas y auditable:

IntelligenceSignal → AutomationRule → AutomationCase → AutomationTask → Timeline

La ejecución es idempotente por `signal + rule`.

## Safety

Las automatizaciones operan sobre tareas y seguimiento, no sobre decisiones punitivas
o de alto impacto. Cualquier resolución significativa requiere intervención humana.
