export const UNIFIED_TOKEN_KEY = "education_os_access_token";

const LEGACY_TOKEN_KEYS = [
  "education_os_admin_token",
  "education_os_coordination_token",
  "education_os_teacher_token",
  "education_os_student_token",
  "education_os_guardian_token",
  "education_os_communications_token",
  "education_os_finance_token",
  "education_os_family_token",
] as const;

export function readAccessToken(): string {
  return sessionStorage.getItem(UNIFIED_TOKEN_KEY)?.trim() ?? "";
}

export function saveAccessToken(token: string): void {
  const normalized = token.trim();
  if (!normalized) {
    clearAccessToken();
    return;
  }

  sessionStorage.setItem(UNIFIED_TOKEN_KEY, normalized);
  for (const key of LEGACY_TOKEN_KEYS) {
    sessionStorage.setItem(key, normalized);
  }
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(UNIFIED_TOKEN_KEY);
  for (const key of LEGACY_TOKEN_KEYS) {
    sessionStorage.removeItem(key);
  }
}
