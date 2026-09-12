export interface UiUserIdentity {
  user_id: string;
  display_name: string;
  login_email: string;
}

export interface UiTenantContext {
  organization_id: string;
  organization_name: string;
  institution_id: string;
  institution_name: string;
  institution_type: string;
}

export interface UiProfileContext {
  staff: boolean;
  student: boolean;
  guardian: boolean;
}

export interface UiBootstrap {
  user: UiUserIdentity;
  tenant: UiTenantContext;
  roles: string[];
  permissions: string[];
  capabilities: Record<string, boolean>;
  profiles: UiProfileContext;
}

export interface Campus {
  id: string;
  institution_id: string;
  name: string;
}
