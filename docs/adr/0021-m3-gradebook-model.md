# ADR 0021 — Gradebook model

Status: Accepted for v0.4.0.

## Decision

El gradebook se estructura en:

GradingPeriod → AssessmentCategory → Assessment → GradeEntry

Las categorías son propias de una CourseOffering y pueden tener peso porcentual.
Las escalas institucionales son configurables mediante GradingScale + GradingScaleBand.

GradeEntry enlaza Assessment + StudentSectionAssignment y repite `section_id` para una FK
compuesta que evita mezclar estudiantes de otra sección.

M3 no calcula todavía promedios finales oficiales ni reglas regulatorias específicas:
esas reglas deben ser configurables y podrán agregarse sin alterar el registro original
de evaluaciones.
