// The report service's routes (TRD §3.4). Shapes come from openapi/report.json.

import type { JobOut, LabelsIn, ReportDownload, ReportOut, ReportPreview, ReportSummary } from './models'
import { api } from './http'

export const reportsApi = {
  /** Admin only (QR-6): starts a label sheet and returns at once; poll `job`. */
  startLabels: (body: LabelsIn) => api.post<JobOut>('/reports/labels', body),
  /** Only the person who asked can read a job. A finished one carries a ten-minute link (never kept). */
  job: (id: string, signal?: AbortSignal) => api.get<JobOut>(`/reports/jobs/${id}`, { signal }),
  /** Staff: the versions of a report, newest first (`visit:{id}` for a visit's). */
  list: (subjectRef: string, signal?: AbortSignal) => api.get<ReportSummary[]>('/reports', { query: { subject_ref: subjectRef }, signal }),
  get: (id: string, signal?: AbortSignal) => api.get<ReportOut>(`/reports/${id}`, { signal }),
  /** RPT-3: draws the draft as it is now. `ready` when that PDF exists; else poll `list`. */
  preview: (id: string) => api.post<ReportPreview>(`/reports/${id}/preview`),
  /** A ten-minute link, never kept (it acts as a password). */
  download: (id: string) => api.get<ReportDownload>(`/reports/${id}/download`),
}
