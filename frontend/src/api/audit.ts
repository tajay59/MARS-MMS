// The audit log (TRD §3.5; PRD AUD-4 to AUD-6). Admins search, export and check; staff read a
// History. Shapes come from openapi/platform.json.

import type { AuditPage, CheckOut, HistoryKind, HistoryPage } from './models'
import { api, download } from './http'

export interface AuditQuery {
  actor?: string
  action?: string
  resource_type?: string
  resource_id?: string
  org_id?: string
  since?: string
  until?: string
  cursor?: number
  limit?: number
}

export const auditApi = {
  /** Admins: newest first; `cursor` is the last `seq` of the page before. */
  events: (query: AuditQuery = {}, signal?: AbortSignal) => api.get<AuditPage>('/audit/events', { query: { ...query }, signal }),
  /** Admins: the same search as a CSV file (at most 50,000 rows; 422 `too_many_records` beyond). */
  exportCsv: (query: AuditQuery = {}) => download('/audit/events/export.csv', { query: { ...query, cursor: undefined, limit: undefined } }),
  /** Staff and the Viewer: who did what to one thing, and when. No values. */
  history: (kind: HistoryKind, id: string, cursor?: number, signal?: AbortSignal) =>
    api.get<HistoryPage>(`/audit/resources/${kind}/${id}`, { query: { cursor, limit: 50 }, signal }),
  /** Admins: queue an integrity check of the chain (202). */
  verify: () => api.post<CheckOut>('/audit/verify'),
  check: (id: string, signal?: AbortSignal) => api.get<CheckOut>(`/audit/checks/${id}`, { signal }),
  /** The last check that finished; 404 until one has. */
  latestCheck: (signal?: AbortSignal) => api.get<CheckOut>('/audit/checks/latest', { signal }),
}
