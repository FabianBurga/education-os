# Education OS — Domain Model M4

```text
M1 Students / Families / Enrollment
                  │
M2 Academic Core  │
        │         │
        └────┬────┘
             ▼
M3 Attendance + Grades
             │
             ▼
     Intelligence Aggregates
       │       │        │
       │       │        └── Academic trends
       │       └─────────── Attendance trends
       └─────────────────── Rector overview
             │
             ▼
     IntelligenceSignal
             │
             ▼
       Human review
```

Signals keep a student/section/period reference plus metric, threshold, severity,
summary and lifecycle status.
