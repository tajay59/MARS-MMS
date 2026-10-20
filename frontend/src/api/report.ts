// The report service's routes (TRD §3.4). Shapes come from openapi/report.json.

import type { JobOut, LabelsIn } from './models'
import { api } from './http'

export const reportsApi = {
  /** Admin only (QR-6): starts a label sheet and returns at once; poll `job`. */
  startLabels: (body: LabelsIn) => api.post<JobOut>('/reports/labels', body),
  /** Only the person who asked can read a job. A finished one carries a ten-minute link (never kept). */
  job: (id: string, signal?: AbortSignal) => api.get<JobOut>(`/reports/jobs/${id}`, { signal }),
}
