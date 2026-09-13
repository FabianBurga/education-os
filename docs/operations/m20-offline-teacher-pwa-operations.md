# M20 Offline Teacher PWA — Operations

Antes de quedar sin red, el docente abre Teacher Workspace, pulsa **Preparar sin conexión** y confirma que la sesión requerida existe. El snapshot caduca a las 24 horas.

Offline: el shell se sirve desde CacheStorage; los datos docentes salen de IndexedDB; el JWT no se persiste fuera de sessionStorage. Los cambios de asistencia quedan `PENDING`.

Al reconectar, **Sincronizar** divide la cola en batches secuenciales de hasta 100 operaciones. `APPLIED` y `REPLAYED` limpian la cola. `CONFLICT`, `REJECTED` o `IDEMPOTENCY_MISMATCH` quedan visibles para resolución explícita.

En conflicto: **Usar servidor** descarta el desired local y adopta server state; **Reintentar local** crea nuevo operation id tomando server state como nuevo base; **Descartar local** elimina la operación local.

Si el snapshot vence, no se permiten nuevas ediciones. Cuando aún existen operaciones pendientes o conflictos, la vista vencida se conserva únicamente para sincronizar o resolver; se elimina al vaciarse la cola. Al cerrar sesión, la aplicación espera la purga de la partición IndexedDB antes de limpiar la sesión.

La capability `teacher.offline_pwa` se instala deshabilitada. El piloto se habilita explícitamente por institución después de validar los gates y el procedimiento de soporte.

Incidente de privacidad: verificar que CacheStorage no contenga URLs `/api/`. No extender TTL ni cachear endpoints autenticados sin revisión de privacidad.

Recovery: backup pre-M20, clone disposable, roundtrip 0018→0019→0018→0019, regresiones nativas, M20 acceptance, backup accepted, restore fingerprint, y solo entonces promover PRIMARY a `0019_m20`.
