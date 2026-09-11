# Education OS — Domain Model M3

```text
CourseOffering ──────────────┐
     │                       │
     ▼                       ▼
ClassSession            AssessmentCategory
     │                       │
     ▼                       ▼
AttendanceRecord        Assessment
     ▲                       │
     │                       ▼
StudentSectionAssignment ─ GradeEntry


AcademicPeriod
     └── GradingPeriod

Institution
     └── GradingScale
          └── GradingScaleBand
```

Attendance y Grades comparten el roster de M2 mediante StudentSectionAssignment.
No se duplica identidad, matrícula ni pertenencia a una sección.
