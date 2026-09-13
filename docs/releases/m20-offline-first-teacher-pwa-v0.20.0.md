# Education OS — M20 Offline-first Teacher PWA v0.20.0

Base congelada: `m19-institution-control-plane-v0.19.0` / `eda4539c02ea02464e248aa221082164664f30de` / DB `0018_m19`.

Objetivo: llevar a PWA instalable el flujo docente de asistencia para sesiones ya creadas, con soporte real sin conexión, privacidad explícita, sincronización idempotente y resolución humana de conflictos.

M20 agrega la capability institucional `teacher.offline_pwa` deshabilitada por defecto para activación controlada por institución, el ledger inmutable `teacher_offline_receipts`, los endpoints `GET /api/v1/teacher/offline/snapshot` y `POST /api/v1/teacher/offline/sync`, Service Worker bajo `/app/`, manifest, IndexedDB por organización/institución/usuario y una UI docente integrada en el frontend unificado.

Límites deliberados v0.20.0: solo asistencia queda disponible offline. Crear sesiones, calificaciones, evaluaciones y tareas siguen online. El Service Worker nunca cachea `/api/*` ni `/health*`; el JWT permanece solo en `sessionStorage`; el snapshot privado vence en 24 horas.

Cada operación offline usa un `operation_id`. El servidor guarda SHA-256 + resultado en un receipt append-only y serializa por operación y por objetivo `(institution, session, student assignment)`. El mismo id+payload responde `REPLAYED`; el mismo id con payload distinto responde `IDEMPOTENCY_MISMATCH`. Si el estado base cambió en servidor, responde `CONFLICT` y exige decisión explícita del docente.

Toda aplicación exitosa registra auditoría `TEACHER_OFFLINE_ATTENDANCE_SYNCED` y evento canónico M18 `teacher.attendance.synced` v1, excluyendo la nota libre del payload canónico.

Migración objetivo: `0019_m20`; tag objetivo tras todos los gates: `m20-offline-first-teacher-pwa-v0.20.0`. Production `v1.0.0` sigue NO RELEASED.
