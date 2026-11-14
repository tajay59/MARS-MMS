// The auth service's routes (TRD §3.1). Shapes come from openapi/auth.json.

import type {
  ApproveIn,
  BrandingIn,
  BrandingOut,
  InviteIn,
  Me,
  MePatch,
  MfaChallenge,
  OrgIn,
  OrgOut,
  OrgPage,
  RecoveryCodesOut,
  RegisterIn,
  TokenResponse,
  TotpSetupOut,
  UserOut,
  UserPage,
  UserStatus,
} from './models'
import { api } from './http'

const pub = { auth: false } as const

export const authApi = {
  register: (body: RegisterIn) => api.post<{ status: string }>('/auth/register', body, pub),
  // `supports_mfa`: this app can show the code step (W22). A person with two-step sign-in gets a
  // challenge instead of a session.
  login: (email: string, password: string) =>
    api.post<TokenResponse | MfaChallenge>('/auth/login', { email, password, supports_mfa: true }, pub),
  loginTotp: (challenge: string, factor: TotpFactor) =>
    api.post<TokenResponse>('/auth/login/totp', { challenge, ...factor }, pub),
  enrolBegin: (challenge: string) =>
    api.post<TotpSetupOut>('/auth/login/totp/enrol/begin', { challenge }, pub),
  enrolConfirm: (challenge: string, code: string) =>
    api.post<TokenResponse>('/auth/login/totp/enrol/confirm', { challenge, code }, pub),
  logout: () => api.post<void>('/auth/logout', undefined, pub),
  requestReset: (email: string) => api.post<{ status: string }>('/auth/password-reset/request', { email }, pub),
  confirmReset: (token: string, password: string) =>
    api.post<void>('/auth/password-reset/confirm', { token, password }, pub),
  acceptInvitation: (token: string, password: string) =>
    api.post<TokenResponse>('/auth/invitations/accept', { token, password }, pub),
  me: () => api.get<Me>('/auth/me'),
  updateMe: (body: MePatch) => api.patch<Me>('/auth/me', body),
}

/** A code from the authenticator app, or one recovery code (exactly one). */
export type TotpFactor = { code: string } | { recovery_code: string }

// Two-step sign-in, managed by a signed-in member of staff (W22)
export const totpApi = {
  begin: (password: string) => api.post<TotpSetupOut>('/auth/me/totp/begin', { password }),
  confirm: (code: string) => api.post<RecoveryCodesOut>('/auth/me/totp/confirm', { code }),
  newRecoveryCodes: (password: string, factor: TotpFactor) =>
    api.post<RecoveryCodesOut>('/auth/me/totp/recovery-codes', { password, ...factor }),
  turnOff: (password: string, factor: TotpFactor) =>
    api.delete<void>('/auth/me/totp', { body: { password, ...factor } }),
}

export interface UserQuery {
  status?: UserStatus
  role?: string
  org_id?: string
  q?: string
  after?: string
  limit?: number
}

export const usersApi = {
  list: (query: UserQuery = {}, signal?: AbortSignal) =>
    api.get<UserPage>('/users', { query: { ...query }, signal }),
  invite: (body: InviteIn) => api.post<UserOut>('/users', body),
  approve: (id: string, body: ApproveIn) => api.post<UserOut>(`/users/${id}/approve`, body),
  reject: (id: string, reason: string) => api.post<UserOut>(`/users/${id}/reject`, { reason }),
  resetTotp: (id: string) => api.post<UserOut>(`/users/${id}/totp/reset`),
}

export const orgsApi = {
  list: (status?: 'active' | 'inactive') => api.get<OrgPage>('/organizations', { query: { status, limit: 200 } }),
  get: (id: string) => api.get<OrgOut>(`/organizations/${id}`),
  create: (body: OrgIn) => api.post<OrgOut>('/organizations', body),
}

// The organization-wide brand colours (decision W4-12): anyone reads them, before sign-in too
export const brandingApi = {
  get: (signal?: AbortSignal) => api.get<BrandingOut>('/auth/branding', { ...pub, signal }),
  save: (body: BrandingIn) => api.put<BrandingOut>('/auth/branding', body),
}
