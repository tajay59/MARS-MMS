// The platform service's notification routes (TRD §3.5). Shapes come from openapi/platform.json.

import type { NotificationPage, NotificationRead } from './models'
import { api } from './http'

export interface NotificationQuery {
  after?: string
  before?: string
  unread?: boolean
  group?: 'requests' | 'comments' | 'accounts'
  limit?: number
}

export const notificationsApi = {
  // Newest first. `after` is what a browser missed while it was away (NOT-2); `before` pages back.
  list: (query: NotificationQuery = {}, signal?: AbortSignal) =>
    api.get<NotificationPage>('/notifications', { query: { ...query }, signal }),
  read: (id: string) => api.post<NotificationRead>(`/notifications/${id}/read`),
  readAll: () => api.post<NotificationRead>('/notifications/read-all'),
}
