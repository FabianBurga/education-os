# Education OS — Domain Model M6

```text
UserAccount
    │
    └── Person
         ├── StaffProfile ──────────────> Internal APIs M1–M5
         │
         └── GuardianProfile
                │
                ▼
     GuardianStudentPortalAccess
                │
                ▼
          StudentProfile
          ├── Enrollment / Section
          ├── Attendance
          └── Grades

FamilyNotice
    ├── student_profile_id = NULL → institutional family notice
    └── student_profile_id = X    → child-specific notice
             │
             ▼
     FamilyNoticeReceipt
```
