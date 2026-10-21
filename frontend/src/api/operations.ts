// The operations service's routes (TRD §3.2). Shapes come from openapi/operations.json.

import type { CalibrationPage, ConfigDiff, ConfigVersionIn, ConfigVersionOut, DocumentIn, DocumentOut, DocumentPage, DocumentPatch, DownloadOut, DueList, Places, QrResolved, QueuePage, RequestDetail, RequestIn, RequestPage, RequestPatch, SensorModelIn, SensorModelList, SensorModelOut, SensorModelPatch, SensorUnitDetail, SensorUnitIn, SensorUnitOut, SensorUnitPage, SensorUnitPatch, StationDetail, StationDocuments, StationIn, StationPage, StationPatch, StationStatus, Workload } from './models'
import { api } from './http'

export interface StationQuery {
  org_id?: string
  country?: string
  type?: string
  status?: StationStatus
  parameter?: string
  q?: string
  after?: string
  limit?: number
}

export const stationsApi = {
  list: (query: StationQuery = {}, signal?: AbortSignal) =>
    api.get<StationPage>('/stations', { query: { ...query }, signal }),
  get: (id: string, signal?: AbortSignal) => api.get<StationDetail>(`/stations/${id}`, { signal }),
  // Staff who write stations (technician, admin): the form (STN-1, STN-2)
  create: (body: StationIn) => api.post<StationDetail>('/stations', body),
  update: (id: string, body: StationPatch) => api.patch<StationDetail>(`/stations/${id}`, body),
  places: (signal?: AbortSignal) => api.get<Places>('/stations/places', { signal }),
}

// Staff only: clients get 403 from these
// Station labels (QR-1 to QR-4, QR-7). The label holds a random token; the lookup is an ordinary
// scoped read, so a station outside the person's organization answers 404, and a replaced code 410.
export const qrApi = {
  resolve: (token: string, signal?: AbortSignal) =>
    api.get<QrResolved>(`/qr/${encodeURIComponent(token)}`, { signal }),
  /** Admin only: gives the station a new token and revokes the old one. */
  regenerate: (stationId: string) => api.post<StationDetail>(`/stations/${stationId}/qr/regenerate`),
}

export interface RequestQuery {
  status?: string[]
  org_id?: string
  country?: string
  station_id?: string
  category?: string
  priority?: string
  q?: string
  from?: string
  to?: string
  after?: string
  limit?: number
}

// Maintenance requests (REQ-1 to REQ-16). A client sees their own organization's only; the server
// decides which actions a person may take (`actions` on the detail) and the page shows only those.
export const requestsApi = {
  list: (query: RequestQuery = {}, signal?: AbortSignal) =>
    api.get<RequestPage>('/requests', { query: { ...query, status: undefined }, signal }),
  get: (id: string, signal?: AbortSignal) => api.get<RequestDetail>(`/requests/${id}`, { signal }),
  // `body.id` is made on the device: sending it again returns the request already made (200)
  create: (body: RequestIn) => api.post<RequestDetail>('/requests', body),
  update: (id: string, body: RequestPatch) => api.patch<RequestDetail>(`/requests/${id}`, body),
  approve: (id: string) => api.post<RequestDetail>(`/requests/${id}/approve`, {}),
  deny: (id: string, reason: string) => api.post<RequestDetail>(`/requests/${id}/deny`, { reason }),
  cancel: (id: string, reason?: string) => api.post<RequestDetail>(`/requests/${id}/cancel`, { reason: reason || null }),
  // Staffing (REQ-7): an admin assigns, a technician claims; release puts it back in the queue.
  // `version` guards a change of staff on a request that is already Assigned.
  assign: (id: string, staffIds: string[], version?: number) =>
    api.post<RequestDetail>(`/requests/${id}/assign`, { staff_ids: staffIds, version }),
  claim: (id: string) => api.post<RequestDetail>(`/requests/${id}/claim`, {}),
  release: (id: string) => api.post<RequestDetail>(`/requests/${id}/release`, {}),
  workload: (signal?: AbortSignal) => api.get<Workload>('/requests/workload', { signal }),
}

// Approved requests nobody has taken, oldest first (staff only; a client has no queue)
export const queueApi = {
  list: (signal?: AbortSignal) => api.get<QueuePage>('/queue', { query: { limit: 200 }, signal }),
}

export const calibrationsApi = {
  due: (withinDays: number, signal?: AbortSignal, filters: { org_id?: string, country?: string } = {}) =>
    api.get<DueList>('/calibrations/due', { query: { within_days: withinDays, ...filters }, signal }),
  list: (query: { station_id?: string, sensor_unit_id?: string, after?: string, limit?: number }, signal?: AbortSignal) =>
    api.get<CalibrationPage>('/calibrations', { query: { ...query }, signal }),
}

export const sensorUnitsApi = {
  get: (id: string, signal?: AbortSignal) => api.get<SensorUnitDetail>(`/sensor-units/${id}`, { signal }),
  list: (query: { model_id?: string, station_id?: string, status?: string, q?: string, after?: string, limit?: number }, signal?: AbortSignal) =>
    api.get<SensorUnitPage>('/sensor-units', { query: { ...query }, signal }),
  // Staff who write (technician, admin). A unit reaches a station only through install (SEN-2).
  create: (body: SensorUnitIn) => api.post<SensorUnitOut>('/sensor-units', body),
  update: (id: string, body: SensorUnitPatch) => api.patch<SensorUnitOut>(`/sensor-units/${id}`, body),
}

// The catalogue of makes and models (staff)
export const sensorModelsApi = {
  list: (query: { kind?: string, q?: string, parameter?: string } = {}, signal?: AbortSignal) =>
    api.get<SensorModelList>('/sensor-models', { query: { ...query }, signal }),
  create: (body: SensorModelIn) => api.post<SensorModelOut>('/sensor-models', body),
  update: (id: string, body: SensorModelPatch) => api.patch<SensorModelOut>(`/sensor-models/${id}`, body),
}

export interface DocumentQuery {
  scope?: 'model' | 'station'
  scope_id?: string
  doc_type?: string
  /** false lists earlier versions too (staff) */
  current?: boolean
  after?: string
  limit?: number
}

// Documents (DOC-1 to DOC-4). A client sees only current, client-visible, clean ones.
export const documentsApi = {
  list: (query: DocumentQuery = {}, signal?: AbortSignal) =>
    api.get<DocumentPage>('/documents', { query: { ...query }, signal }),
  forStation: (stationId: string, signal?: AbortSignal) =>
    api.get<StationDocuments>(`/stations/${stationId}/documents`, { signal }),
  get: (id: string, signal?: AbortSignal) => api.get<DocumentOut>(`/documents/${id}`, { signal }),
  // Staff who write (technician, admin). `body.id` and `body.media_id` are made on the device.
  create: (body: DocumentIn) => api.post<DocumentOut>('/documents', body),
  update: (id: string, body: DocumentPatch) => api.patch<DocumentOut>(`/documents/${id}`, body),
  /** A ten-minute link for the file; never kept (TRD §7.6) */
  download: (id: string, inline = true) =>
    api.get<DownloadOut>(`/documents/${id}/download`, { query: { inline } }),
}

// Configuration versions (CFG-1 to CFG-3). Staff only.
export const configVersionsApi = {
  list: (stationId: string, signal?: AbortSignal) =>
    api.get<ConfigVersionOut[]>(`/stations/${stationId}/config-versions`, { signal }),
  create: (stationId: string, body: ConfigVersionIn) =>
    api.post<ConfigVersionOut>(`/stations/${stationId}/config-versions`, body),
  diff: (stationId: string, version: number, against?: number, signal?: AbortSignal) =>
    api.get<ConfigDiff>(`/stations/${stationId}/config-versions/${version}/diff`, { query: { against }, signal }),
}
