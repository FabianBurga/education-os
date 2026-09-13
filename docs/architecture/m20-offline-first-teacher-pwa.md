# M20 Offline-first Teacher PWA — Architecture Contract

```text
React/Vite /app
  ├─ Service Worker -> CacheStorage (solo shell/estáticos)
  ├─ sessionStorage -> JWT + último UiBootstrap de la pestaña
  └─ IndexedDB -> snapshot docente + cola de asistencia
                      |
                      v reconexión
FastAPI /teacher/offline/sync
  ├─ teacher.attendance.manage + teaching assignment scope
  ├─ optimistic base comparison
  ├─ advisory transaction locks ordenados por operation_id y objetivo
  ├─ immutable idempotency receipt
  ├─ attendance upsert
  ├─ audit
  └─ M18 canonical event -> Event Ledger
```

No hay event sourcing ni microservicios. PostgreSQL continúa como fuente operacional. M18 continúa como único Event Ledger y M19 como único Control Plane.

La cola mantiene una operación local por `(session, student assignment)`. Los cambios locales posteriores reemplazan el desired state sin perder el server base original. La sincronización compara record id, attendance code, minutes late y note. Si cambió, no sobrescribe automáticamente. El servidor adquiere locks por operación y por `(institution, session, student assignment)` en orden lexicográfico antes de leer estado; así, dos operation ids concurrentes sobre el mismo objetivo no pueden aplicar ambos.

Al cerrar sesión, la purga de IndexedDB de la partición docente se espera antes de limpiar la sesión. Un snapshot vencido no admite nuevas ediciones; si aún tiene operaciones pendientes o conflictos se conserva para sincronizarlos o resolverlos y se elimina cuando la cola queda vacía.

`teacher_offline_receipts` tiene RLS + FORCE RLS, SELECT/INSERT runtime, actor-bound access, helper SECURITY DEFINER con `search_path=public`, y triggers que rechazan UPDATE/DELETE/TRUNCATE.
