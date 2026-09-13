import type { UiBootstrap } from "../types/bootstrap";
export const UNIFIED_TOKEN_KEY="education_os_access_token";
export const UNIFIED_BOOTSTRAP_KEY="education_os_bootstrap_cache";
const LEGACY_TOKEN_KEYS=["education_os_admin_token","education_os_coordination_token","education_os_teacher_token","education_os_student_token","education_os_guardian_token","education_os_communications_token","education_os_finance_token","education_os_family_token"] as const;
export function readAccessToken():string{return sessionStorage.getItem(UNIFIED_TOKEN_KEY)?.trim()??"";}
export function saveAccessToken(token:string):void{const normalized=token.trim();if(!normalized){clearAccessToken();return;}sessionStorage.setItem(UNIFIED_TOKEN_KEY,normalized);for(const key of LEGACY_TOKEN_KEYS)sessionStorage.setItem(key,normalized);}
export function saveCachedBootstrap(bootstrap:UiBootstrap):void{sessionStorage.setItem(UNIFIED_BOOTSTRAP_KEY,JSON.stringify(bootstrap));}
export function readCachedBootstrap():UiBootstrap|null{const raw=sessionStorage.getItem(UNIFIED_BOOTSTRAP_KEY);if(!raw)return null;try{return JSON.parse(raw) as UiBootstrap;}catch{sessionStorage.removeItem(UNIFIED_BOOTSTRAP_KEY);return null;}}
export function clearCachedBootstrap():void{sessionStorage.removeItem(UNIFIED_BOOTSTRAP_KEY);}
export function clearAccessToken():void{sessionStorage.removeItem(UNIFIED_TOKEN_KEY);sessionStorage.removeItem(UNIFIED_BOOTSTRAP_KEY);for(const key of LEGACY_TOKEN_KEYS)sessionStorage.removeItem(key);}
