# Education OS — Backup / Restore

Backup:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\backup_education_os.ps1
```

Verificación:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_backup_hash.ps1 `
  -BackupFile ".\backups\education_os_YYYYMMDD_HHMMSS.dump"
```

Restore de ensayo, siempre sobre una base separada:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\restore_education_os.ps1 `
  -BackupFile ".\backups\education_os_YYYYMMDD_HHMMSS.dump" `
  -TargetDatabase "education_os_restore_test" `
  -ConfirmRestore
```

Nunca ensayar restore destructivo sobre la única base disponible.
