// The operations service's routes (TRD §3.2). Shapes come from openapi/operations.json.

import type { CalibrationPage, DueList, Places, SensorUnitDetail, StationDetail, StationIn, StationPage, StationPatch, StationStatus } from './models'
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
export const calibrationsApi = {
  due: (withinDays: number, signal?: AbortSignal) =>
    api.get<DueList>('/calibrations/due', { query: { within_days: withinDays }, signal }),
  list: (query: { station_id?: string, sensor_unit_id?: string, after?: string, limit?: number }, signal?: AbortSignal) =>
    api.get<CalibrationPage>('/calibrations', { query: { ...query }, signal }),
}

export const sensorUnitsApi = {
  get: (id: string, signal?: AbortSignal) => api.get<SensorUnitDetail>(`/sensor-units/${id}`, { signal }),
}
