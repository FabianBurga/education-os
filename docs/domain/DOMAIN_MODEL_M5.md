# Education OS — Domain Model M5

```text
IntelligenceSignal
       │
       ▼
AutomationRule
       │
       ▼
AutomationCase
       │
       ├── AutomationTask
       │      ├── OPEN
       │      ├── ACKNOWLEDGED
       │      ├── ESCALATED
       │      └── COMPLETED
       │
       └── AutomationTimelineEvent
```

El motor de automatización conecta inteligencia con trabajo institucional trazable.
