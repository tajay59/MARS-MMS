// The auth service's routes (TRD §3.1). Shapes come from openapi/auth.json.

import type {
  ApproveIn,
  BrandingIn,
  BrandingOut,
  InviteIn,
  Me,
  MePatch,
  OrgIn,
  OrgOut,
  OrgPage,
  RegisterIn,
  TokenResponse,
  UserOut,
  UserPage,
  UserStatus,
} from './models'
import { api } from './http'

const pub = { auth: false } as const

export const authApi = {
  register: (body: RegisterIn) => api.post<{ status: string }>('/auth/register', body, pub),
  login: (email: string, password: string) =>
    api.post<TokenResponse>('/auth/login', { email, password }, pub),
  logout: () => api.post<void>('/auth/logout', undefined, pub),
  requestReset: (email: string) => api.post<{ status: string }>('/auth/password-reset/request', { email }, pub),
  confirmReset: (token: string, password: string) =>
    api.post<void>('/auth/password-reset/confirm', { token, password }, pub),
  acceptInvitation: (token: string, password: string) =>
    api.post<TokenResponse>('/auth/invitations/accept', { token, password }, pub),
  me: () => api.get<Me>('/auth/me'),
  updateMe: (body: MePatch) => api.patch<Me>('/auth/me', body),
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
