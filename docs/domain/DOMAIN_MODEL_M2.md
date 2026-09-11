# Education OS — Domain Model M2

```text
Organization
└── Institution
    ├── Campus
    ├── AcademicPeriod
    ├── AcademicLevel
    │   └── GradeLevel
    │       ├── Section ───────────────┐
    │       └── CurriculumPlan         │
    │           └── CurriculumSubject │
    │               └── Subject       │
    │                                 │
    ├── Subject ───────────────────────┤
    │                                 ▼
    │                         CourseOffering
    │                         ├── TeachingAssignment ── StaffProfile
    │                         └── ScheduleSlot
    │
    └── Enrollment ── StudentSectionAssignment ── Section
```

M3 añadirá asistencia y calificaciones sobre estas unidades académicas sin duplicar
estudiantes, docentes, períodos, secciones ni asignaturas.
