// The report service's routes (TRD §3.4). Shapes come from openapi/report.json.

import type { JobOut, LabelsIn, ReportContentPatch, ReportCorrection, ReportDownload, ReportOut, ReportPreview, ReportReopenIn, ReportSignIn, ReportSummary } from './models'
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
  /** Whether a visit's final report is being corrected (a client's only sight of a reopen). */
  correction: (visitId: string, signal?: AbortSignal) => api.get<ReportCorrection>('/reports/correction', { query: { visit_id: visitId }, signal }),
  /** RPT-2: change the narrative or the photo choice of a draft. A stale `content_version` is 409 `content_changed` with `current`. */
  edit: (id: string, body: ReportContentPatch) => api.patch<ReportOut>(`/reports/${id}/content`, body),
  /** RPT-4: sign the draft as it stands. 409 `already_signed` or `content_changed`. Never queued: it needs a connection. */
  sign: (id: string, body: ReportSignIn) => api.post<ReportOut>(`/reports/${id}/sign`, body),
  /** RPT-5: the lead or an admin, once the lead has signed. Answers at once; the report is `finalizing` until the worker is done. */
  finalize: (id: string) => api.post<ReportOut>(`/reports/${id}/finalize`),
  /** RPT-6: an admin reopens a final report as the next draft version. */
  reopen: (id: string, body: ReportReopenIn) => api.post<ReportOut>(`/reports/${id}/reopen`, body),
}
