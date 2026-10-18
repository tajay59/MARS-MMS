import type { StationDetail, StationIn, StationPatch, StationStatus } from '@/api/models'
import type { ApiError } from '@/api/problem'

/*
  The station form (PRD STN-1, STN-2; approved mock-up "Station form"). No Vue here, so Vitest
  covers it directly. The form keeps every value as text, as typed; `createBody` and `patchBody`
  turn it into the API's shapes, and `validate` says what the server would, in the words of DBD
  "Voice and microcopy". The server checks everything again (rule 12).
*/

export type FieldKey = keyof StationFormValues
export type FieldErrors = Partial<Record<FieldKey, string>>

export interface StationFormValues {
  code: string
  externalId: string
  name: string
  ownerOrgId: string
  type: string
  country: string
  timeZone: string
  region: string
  latitude: string
  longitude: string
  elevation: string
  accessNotes: string
  parameters: string[]
  loggerModel: string
  loggerSerial: string
  loggerFirmware: string
  commsType: string
  commsProvider: string
  commsIdentifier: string
  panelW: string
  batteryAh: string
  controller: string
  status: StationStatus
  installDate: string
}

// The server's limits (api/stations/schemas.py, domain/stations/stations.py)
export const CODE_MIN = 2
export const CODE_MAX = 32
export const TEXT_MAX = 120
export const NOTES_MAX = 2000
export const MAX_PARAMETERS = 40
export const PARAMETER_MAX = 32
const PARAMETER_PATTERN = new RegExp(`^[A-Z][A-Z0-9_]{0,${PARAMETER_MAX - 1}}$`)
const EXTERNAL_ID_PATTERN = /^[\w.:-]{1,64}$/

export function emptyValues (): StationFormValues {
  return {
    code: '',
    externalId: '',
    name: '',
    ownerOrgId: '',
    type: '',
    country: '',
    timeZone: '',
    region: '',
    latitude: '',
    longitude: '',
    elevation: '',
    accessNotes: '',
    parameters: [],
    loggerModel: '',
    loggerSerial: '',
    loggerFirmware: '',
    commsType: '',
    commsProvider: '',
    commsIdentifier: '',
    panelW: '',
    batteryAh: '',
    controller: '',
    status: 'operational',
    installDate: '',
  }
}

type Bag = Record<string, unknown> | null | undefined

function text (bag: Bag, key: string): string {
  const value = bag?.[key]
  return typeof value === 'string' ? value : (typeof value === 'number' ? String(value) : '')
}

function numberText (value: number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value)
}

/** The form's values for a saved station. */
export function valuesOf (station: StationDetail): StationFormValues {
  return {
    code: station.code,
    externalId: station.external_id ?? '',
    name: station.name,
    ownerOrgId: station.owner_org_id,
    type: station.type ?? '',
    country: station.country,
    timeZone: station.time_zone,
    region: station.region ?? '',
    latitude: numberText(station.latitude),
    longitude: numberText(station.longitude),
    elevation: numberText(station.elevation_m),
    accessNotes: station.access_notes ?? '',
    parameters: [...station.parameters],
    loggerModel: text(station.logger, 'model'),
    loggerSerial: text(station.logger, 'serial'),
    loggerFirmware: text(station.logger, 'firmware'),
    commsType: text(station.comms, 'type'),
    commsProvider: text(station.comms, 'provider'),
    commsIdentifier: text(station.comms, 'identifier'),
    panelW: text(station.power, 'panel_w'),
    batteryAh: text(station.power, 'battery_ah'),
    controller: text(station.power, 'controller'),
    status: station.status as StationStatus,
    installDate: station.install_date ?? '',
  }
}

// --- Small parsers ----------------------------------------------------------------------------

/** A parameter code as the server stores it: trimmed, upper case. */
export function normalizeParameter (value: string): string {
  return value.trim().toUpperCase()
}

/** The number typed in a field; null when empty, NaN when it isn't one (a comma is accepted). */
export function parseNumber (value: string): number | null {
  const trimmed = value.trim().replace(',', '.')
  return trimmed === '' ? null : (/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(trimmed) ? Number(trimmed) : Number.NaN)
}

/** The country's only time zone, if it has exactly one (the server's `default_time_zone`). */
export function onlyZone (country: string, zones: Readonly<Record<string, readonly string[]>>): string | null {
  const found = zones[country]
  return found?.length === 1 ? (found[0] ?? null) : null
}

function blank (value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

// --- Checks -----------------------------------------------------------------------------------

function within (value: number | null, min: number, max: number): boolean {
  return value === null || (!Number.isNaN(value) && value >= min && value <= max)
}

/** Latitude and longitude: both or neither, and both when the station needs a place. */
function validateLocation (v: StationFormValues, needBoth: boolean): FieldErrors {
  const e: FieldErrors = {}
  const lat = parseNumber(v.latitude)
  const lon = parseNumber(v.longitude)
  if (!within(lat, -90, 90)) {
    e.latitude = 'Use a number from -90 to 90'
  }
  if (!within(lon, -180, 180)) {
    e.longitude = 'Use a number from -180 to 180'
  }
  if (!e.latitude && !e.longitude) {
    if (lat === null && lon === null) {
      if (needBoth) {
        e.latitude = 'Enter the latitude'
        e.longitude = 'Enter the longitude'
      }
    } else if (lat === null) {
      e.latitude = 'Add the latitude too'
    } else if (lon === null) {
      e.longitude = 'Add the longitude too'
    }
  }
  return e
}

/**
 * What is wrong with the values. `hadLocation`: an existing station with coordinates can't lose
 * them here (the API has no way to clear one); a new station needs them (STN-1).
 */
export function validate (v: StationFormValues, mode: 'new' | 'edit', hadLocation = false): FieldErrors {
  const e: FieldErrors = {}
  const code = v.code.trim()
  if (code.length < CODE_MIN || code.length > CODE_MAX) {
    e.code = `Use ${CODE_MIN} to ${CODE_MAX} characters`
  }
  if (!v.name.trim()) {
    e.name = 'Enter the station’s name'
  } else if (v.name.trim().length > TEXT_MAX) {
    e.name = `Use at most ${TEXT_MAX} characters`
  }
  if (v.externalId.trim() && !EXTERNAL_ID_PATTERN.test(v.externalId.trim())) {
    e.externalId = 'Use letters, numbers and . _ : - only, up to 64 characters'
  }
  if (mode === 'new' && !v.ownerOrgId) {
    e.ownerOrgId = 'Choose the owner organization'
  }
  if (v.type.trim().length > 60) {
    e.type = 'Use at most 60 characters'
  }
  if (!v.country) {
    e.country = 'Choose a country'
  }
  if (!v.timeZone) {
    e.timeZone = 'Choose a time zone'
  }
  if (v.region.trim().length > TEXT_MAX) {
    e.region = `Use at most ${TEXT_MAX} characters`
  }

  Object.assign(e, validateLocation(v, mode === 'new' || hadLocation))

  if (!within(parseNumber(v.elevation), -500, 9000)) {
    e.elevation = 'Use a number from -500 to 9000'
  }
  if (v.accessNotes.trim().length > NOTES_MAX) {
    e.accessNotes = `Use at most ${NOTES_MAX} characters`
  }
  if (v.parameters.length > MAX_PARAMETERS) {
    e.parameters = `Use at most ${MAX_PARAMETERS} parameters`
  } else if (v.parameters.some(p => !PARAMETER_PATTERN.test(p))) {
    e.parameters = 'Start each code with a letter; use letters, numbers and _ only'
  }
  for (const [key, label] of [
    ['loggerModel', 'logger model'], ['loggerSerial', 'logger serial'], ['loggerFirmware', 'firmware'],
    ['commsType', 'link type'], ['commsProvider', 'provider'], ['commsIdentifier', 'identifier'],
    ['controller', 'controller'],
  ] as const) {
    if (v[key].trim().length > TEXT_MAX) {
      e[key] = `Use at most ${TEXT_MAX} characters for the ${label}`
    }
  }
  for (const key of ['panelW', 'batteryAh'] as const) {
    if (!within(parseNumber(v[key]), 0, 1_000_000)) {
      e[key] = 'Use a number of 0 or more'
    }
  }
  if (v.installDate && !/^\d{4}-\d{2}-\d{2}$/.test(v.installDate)) {
    e.installDate = 'Use a date such as 2026-03-14'
  }
  return e
}

// --- Bodies -----------------------------------------------------------------------------------

type Logger = NonNullable<StationIn['logger']>
type Comms = NonNullable<StationIn['comms']>
type Power = NonNullable<StationIn['power']>

function logger (v: StationFormValues): Logger | null {
  const found: Logger = { model: blank(v.loggerModel), serial: blank(v.loggerSerial), firmware: blank(v.loggerFirmware) }
  return found.model || found.serial || found.firmware ? found : null
}

function comms (v: StationFormValues): Comms | null {
  const found: Comms = { type: blank(v.commsType), provider: blank(v.commsProvider), identifier: blank(v.commsIdentifier) }
  return found.type || found.provider || found.identifier ? found : null
}

function power (v: StationFormValues): Power | null {
  const found: Power = { panel_w: parseNumber(v.panelW), battery_ah: parseNumber(v.batteryAh), controller: blank(v.controller) }
  return found.panel_w !== null || found.battery_ah !== null || found.controller ? found : null
}

/** What the API takes to make a station. Call it with values `validate` accepted. */
export function createBody (v: StationFormValues): StationIn {
  return {
    code: v.code.trim(),
    name: v.name.trim(),
    owner_org_id: v.ownerOrgId,
    country: v.country,
    time_zone: v.timeZone,
    latitude: parseNumber(v.latitude) ?? 0,
    longitude: parseNumber(v.longitude) ?? 0,
    external_id: blank(v.externalId),
    type: blank(v.type),
    region: blank(v.region),
    elevation_m: parseNumber(v.elevation),
    parameters: v.parameters,
    logger: logger(v),
    comms: comms(v),
    power: power(v),
    install_date: blank(v.installDate),
    status: v.status,
    access_notes: blank(v.accessNotes),
  }
}

function same (a: unknown, b: unknown): boolean {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null)
}

/** The group as the station has it, with the keys the API takes, to tell what the person changed. */
function stored (bag: Bag, keys: readonly string[]): Record<string, unknown> | null {
  const found = Object.fromEntries(keys.map(key => [key, bag?.[key] ?? null]))
  return Object.values(found).some(value => value !== null) ? found : null
}

/**
 * Only what the person changed: a station imported with a value the form would refuse (an odd
 * external ID, say) can still be edited elsewhere. Latitude and longitude go together.
 */
export function patchBody (v: StationFormValues, station: StationDetail): Omit<StationPatch, 'version'> {
  const body: Omit<StationPatch, 'version'> = {}
  const was = valuesOf(station)
  if (v.code.trim() !== was.code) {
    body.code = v.code.trim()
  }
  if (v.name.trim() !== was.name) {
    body.name = v.name.trim()
  }
  if (v.externalId.trim() !== was.externalId) {
    body.external_id = blank(v.externalId)
  }
  if (v.type.trim() !== was.type) {
    body.type = blank(v.type)
  }
  if (v.country !== was.country) {
    body.country = v.country
  }
  if (v.timeZone !== was.timeZone) {
    body.time_zone = v.timeZone
  }
  if (v.region.trim() !== was.region) {
    body.region = blank(v.region)
  }
  if (parseNumber(v.latitude) !== parseNumber(was.latitude) || parseNumber(v.longitude) !== parseNumber(was.longitude)) {
    body.latitude = parseNumber(v.latitude)
    body.longitude = parseNumber(v.longitude)
  }
  if (parseNumber(v.elevation) !== parseNumber(was.elevation)) {
    body.elevation_m = parseNumber(v.elevation)
  }
  if (v.accessNotes.trim() !== was.accessNotes) {
    body.access_notes = blank(v.accessNotes)
  }
  if (!same(sortedCopy(v.parameters), sortedCopy(was.parameters))) {
    body.parameters = v.parameters
  }
  if (!same(logger(v), stored(station.logger, ['model', 'serial', 'firmware']))) {
    body.logger = logger(v)
  }
  if (!same(comms(v), stored(station.comms, ['type', 'provider', 'identifier']))) {
    body.comms = comms(v)
  }
  if (!same(power(v), stored(station.power, ['panel_w', 'battery_ah', 'controller']))) {
    body.power = power(v)
  }
  if (v.status !== was.status) {
    body.status = v.status
  }
  if (v.installDate !== was.installDate) {
    body.install_date = blank(v.installDate)
  }
  return body
}

function sortedCopy (items: readonly string[]): string[] {
  // A fresh copy: sorting it in place is safe
  // eslint-disable-next-line unicorn/no-array-sort
  return [...items].sort()
}

/** True when saving would change nothing. */
export function isUnchanged (v: StationFormValues, station: StationDetail): boolean {
  return Object.keys(patchBody(v, station)).length === 0
}

// --- Server answers ---------------------------------------------------------------------------

const API_FIELDS: Record<string, FieldKey> = {
  code: 'code',
  name: 'name',
  external_id: 'externalId',
  owner_org_id: 'ownerOrgId',
  type: 'type',
  country: 'country',
  time_zone: 'timeZone',
  region: 'region',
  latitude: 'latitude',
  longitude: 'longitude',
  elevation_m: 'elevation',
  access_notes: 'accessNotes',
  parameters: 'parameters',
  logger: 'loggerModel',
  comms: 'commsType',
  power: 'panelW',
  status: 'status',
  install_date: 'installDate',
}

export type SaveProblem
  = | { kind: 'fields', errors: FieldErrors, message: string | null }
    | { kind: 'stale' }
    | { kind: 'other', message: string }

/** What a failed save means for the form (the answers are in api/stations/station_routes.py). */
export function problemOf (error: ApiError): SaveProblem {
  switch (error.code) {
    case 'version_conflict': {
      return { kind: 'stale' }
    }
    case 'code_taken': {
      return { kind: 'fields', errors: { code: 'Another station has this code. Use a different one.' }, message: null }
    }
    case 'external_id_taken': {
      return { kind: 'fields', errors: { externalId: 'Another station has this external ID.' }, message: null }
    }
    case 'parameter_in_use': {
      return { kind: 'fields', errors: { parameters: error.detail }, message: null }
    }
    case 'org_inactive': {
      return { kind: 'fields', errors: { ownerOrgId: 'Choose an active organization.' }, message: null }
    }
    default: {
      const errors: FieldErrors = {}
      for (const [field, message] of Object.entries(error.fieldErrors())) {
        const key = API_FIELDS[field]
        if (key) {
          errors[key] = message
        }
      }
      if (Object.keys(errors).length > 0) {
        return { kind: 'fields', errors, message: null }
      }
      return error.status === 422 || error.status === 409
        ? { kind: 'fields', errors: {}, message: error.detail }
        : { kind: 'other', message: 'We couldn’t save the station. Try again in a moment.' }
    }
  }
}
