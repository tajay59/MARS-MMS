import type { SensorModelIn, SensorModelOut, SensorModelPatch, SensorSpec, SensorUnitIn, SensorUnitOut, SensorUnitPatch } from '@/api/models'
import type { ApiError } from '@/api/problem'
import { PARAMETER_PATTERN } from '@/features/stations/stationFormModel'
import { kinds } from '@/features/stations/stations'

/*
  The sensor model and sensor unit forms (PRD SEN-1, SEN-2, CAL-3; approved mock-up "W6 forms").
  No Vue here, so Vitest covers it directly. Values are kept as typed text; the builders turn them
  into the API's shapes, and `validate*` says what the server would. The server checks everything
  again (rule 12).
*/

export const TEXT_MAX = 120
export const SERIAL_MAX = 80
export const NOTES_MAX = 2000
export const INTERVAL_MIN = 1
export const INTERVAL_MAX = 3650
/** A model's parameters (SensorModelIn allows 20). */
export const MODEL_MAX_PARAMETERS = 20
/** A model's technical specifications (SensorModelIn allows 8). */
export const MODEL_MAX_SPECS = 8

export const kindOptions = Object.entries(kinds).map(([value, label]) => ({ value, label }))

/** The statuses a person can set on a unit; "installed" comes only from installing it. */
export const unitStatusOptions = [
  { value: 'in_stock', label: 'In stock' },
  { value: 'in_repair', label: 'In repair' },
  { value: 'retired', label: 'Retired' },
] as const

export type EditableStatus = (typeof unitStatusOptions)[number]['value']

/** `{ field: message }` for the first problem on each field. */
export type Errors<K extends string> = Partial<Record<K, string>>

export type SaveProblem<K extends string>
  = | { kind: 'stale' }
    | { kind: 'fields', errors: Errors<K>, message: string | null }
    | { kind: 'other', message: string }

function blank (value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

/** Whole days typed in a field: null when empty, NaN when it isn't a whole number. */
export function parseDays (value: string): number | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : (/^\d+$/.test(trimmed) ? Number(trimmed) : Number.NaN)
}

function checkInterval (value: string): string | undefined {
  const days = parseDays(value)
  if (days === null) {
    return undefined
  }
  return Number.isNaN(days) || days < INTERVAL_MIN || days > INTERVAL_MAX
    ? `Use a whole number of days from ${INTERVAL_MIN} to ${INTERVAL_MAX}`
    : undefined
}

function same (a: unknown, b: unknown): boolean {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null)
}

// --- Sensor model -----------------------------------------------------------------------------

/** One line of specifications as typed: `Operating range`, `-80 to +60 °C`, and an optional second line. */
export interface SpecValues {
  label: string
  value: string
  detail: string
}

export interface ModelValues {
  kind: string
  manufacturer: string
  model: string
  parameters: string[]
  interval: string
  specs: SpecValues[]
}

export type ModelField = keyof ModelValues

export function emptyModel (): ModelValues {
  return { kind: 'sensor', manufacturer: '', model: '', parameters: [], interval: '', specs: [] }
}

export function modelValues (model: SensorModelOut): ModelValues {
  return {
    kind: model.kind,
    manufacturer: model.manufacturer,
    model: model.model,
    parameters: [...model.parameters],
    interval: model.default_calibration_interval_days === null ? '' : String(model.default_calibration_interval_days),
    specs: model.specs.map(s => ({ label: s.label, value: s.value, detail: s.detail ?? '' })),
  }
}

/** The specs as the API takes them: a line needs both its label and its value, so half-typed ones are dropped. */
export function specsBody (specs: readonly SpecValues[]): SensorSpec[] {
  return specs
    .filter(s => s.label.trim() && s.value.trim())
    .map(s => ({ label: s.label.trim(), value: s.value.trim(), detail: blank(s.detail) }))
}

export function validateModel (v: ModelValues): Errors<ModelField> {
  const e: Errors<ModelField> = {}
  if (!v.manufacturer.trim()) {
    e.manufacturer = 'Enter the make'
  } else if (v.manufacturer.trim().length > TEXT_MAX) {
    e.manufacturer = `Use at most ${TEXT_MAX} characters`
  }
  if (!v.model.trim()) {
    e.model = 'Enter the model'
  } else if (v.model.trim().length > TEXT_MAX) {
    e.model = `Use at most ${TEXT_MAX} characters`
  }
  if (v.parameters.length > MODEL_MAX_PARAMETERS) {
    e.parameters = `Use at most ${MODEL_MAX_PARAMETERS} parameters`
  } else if (v.parameters.some(p => !PARAMETER_PATTERN.test(p))) {
    e.parameters = 'Start each code with a letter; use letters, numbers and _ only'
  }
  const interval = checkInterval(v.interval)
  if (interval) {
    e.interval = interval
  }
  if (v.specs.length > MODEL_MAX_SPECS) {
    e.specs = `Use at most ${MODEL_MAX_SPECS} specifications`
  } else if (v.specs.some(s => (s.label.trim() === '') !== (s.value.trim() === ''))) {
    e.specs = 'Give each specification a name and a value'
  } else if (v.specs.some(s => s.label.trim().length > TEXT_MAX || s.value.trim().length > TEXT_MAX || s.detail.trim().length > TEXT_MAX)) {
    e.specs = `Use at most ${TEXT_MAX} characters in each field`
  }
  return e
}

export function modelCreateBody (v: ModelValues): SensorModelIn {
  return {
    kind: v.kind as SensorModelIn['kind'],
    manufacturer: v.manufacturer.trim(),
    model: v.model.trim(),
    parameters: v.parameters,
    default_calibration_interval_days: parseDays(v.interval),
    specs: specsBody(v.specs),
  }
}

/** Only what changed, with the version the person was looking at; null when nothing did. */
export function modelPatchBody (v: ModelValues, was: SensorModelOut): SensorModelPatch | null {
  const body: SensorModelPatch = { version: was.version }
  let changed = false
  if (v.kind !== was.kind) {
    body.kind = v.kind as SensorModelIn['kind']
    changed = true
  }
  if (v.manufacturer.trim() !== was.manufacturer) {
    body.manufacturer = v.manufacturer.trim()
    changed = true
  }
  if (v.model.trim() !== was.model) {
    body.model = v.model.trim()
    changed = true
  }
  if (!same(v.parameters, was.parameters)) {
    body.parameters = v.parameters
    changed = true
  }
  const days = parseDays(v.interval)
  if (days !== was.default_calibration_interval_days) {
    body.default_calibration_interval_days = days
    changed = true
  }
  const specs = specsBody(v.specs)
  if (!same(specs, was.specs.map(s => ({ label: s.label, value: s.value, detail: s.detail ?? null })))) {
    body.specs = specs
    changed = true
  }
  return changed ? body : null
}

const MODEL_API_FIELDS: Record<string, ModelField> = {
  kind: 'kind',
  manufacturer: 'manufacturer',
  model: 'model',
  parameters: 'parameters',
  default_calibration_interval_days: 'interval',
  specs: 'specs',
}

export function modelProblem (error: ApiError, typed: Pick<ModelValues, 'manufacturer' | 'model'>): SaveProblem<ModelField> {
  if (error.code === 'version_conflict') {
    return { kind: 'stale' }
  }
  if (error.code === 'model_taken') {
    return {
      kind: 'fields',
      errors: { model: `${typed.manufacturer.trim()} ${typed.model.trim()} is already in the catalogue.` },
      message: null,
    }
  }
  const errors: Errors<ModelField> = {}
  for (const [field, message] of Object.entries(error.fieldErrors())) {
    const key = MODEL_API_FIELDS[field]
    if (key) {
      errors[key] = message
    }
  }
  if (Object.keys(errors).length > 0) {
    return { kind: 'fields', errors, message: null }
  }
  return error.status === 422 || error.status === 409
    ? { kind: 'fields', errors: {}, message: error.detail }
    : { kind: 'other', message: 'We couldn’t save the model. Try again in a moment.' }
}

// --- Sensor unit ------------------------------------------------------------------------------

export interface UnitValues {
  serial: string
  status: EditableStatus
  /** yyyy-mm-dd; only when adding (later calibrations are recorded on the station) */
  lastCalibrated: string
  interval: string
  notes: string
}

export type UnitField = keyof UnitValues

export function emptyUnit (): UnitValues {
  return { serial: '', status: 'in_stock', lastCalibrated: '', interval: '', notes: '' }
}

export function unitValues (unit: SensorUnitOut): UnitValues {
  return {
    serial: unit.serial,
    status: unit.status === 'in_repair' || unit.status === 'retired' ? unit.status : 'in_stock',
    lastCalibrated: '',
    interval: unit.calibration_interval_days === null ? '' : String(unit.calibration_interval_days),
    notes: unit.notes ?? '',
  }
}

/** Today as yyyy-mm-dd on this device, for the "not in the future" check. */
export function localToday (now = new Date()): string {
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

export function validateUnit (v: UnitValues, adding: boolean, today = localToday()): Errors<UnitField> {
  const e: Errors<UnitField> = {}
  const serial = v.serial.trim()
  if (!serial) {
    e.serial = 'Enter the serial number'
  } else if (serial.length > SERIAL_MAX) {
    e.serial = `Use at most ${SERIAL_MAX} characters`
  }
  const interval = checkInterval(v.interval)
  if (interval) {
    e.interval = interval
  }
  if (adding && v.lastCalibrated) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(v.lastCalibrated) || Number.isNaN(Date.parse(`${v.lastCalibrated}T00:00:00Z`))) {
      e.lastCalibrated = 'Enter a date'
    } else if (v.lastCalibrated > today) {
      e.lastCalibrated = 'A calibration can’t be in the future'
    }
  }
  if (v.notes.trim().length > NOTES_MAX) {
    e.notes = `Use at most ${NOTES_MAX} characters`
  }
  return e
}

export function unitCreateBody (v: UnitValues, modelId: string): SensorUnitIn {
  return {
    model_id: modelId,
    serial: v.serial.trim(),
    status: v.status,
    calibration_interval_days: parseDays(v.interval),
    last_calibrated_at: v.lastCalibrated ? `${v.lastCalibrated}T00:00:00Z` : null,
    notes: blank(v.notes),
  }
}

/**
 * Only what changed. A unit that is installed keeps its status here: it leaves a station only
 * through "Remove" there (the server refuses a status change).
 */
export function unitPatchBody (v: UnitValues, was: SensorUnitOut): SensorUnitPatch | null {
  const body: SensorUnitPatch = { version: was.version }
  let changed = false
  if (v.serial.trim() !== was.serial) {
    body.serial = v.serial.trim()
    changed = true
  }
  if (was.status !== 'installed' && v.status !== was.status) {
    body.status = v.status
    changed = true
  }
  const days = parseDays(v.interval)
  if (days !== was.calibration_interval_days) {
    body.calibration_interval_days = days
    changed = true
  }
  if (blank(v.notes) !== (was.notes ?? null)) {
    body.notes = blank(v.notes)
    changed = true
  }
  return changed ? body : null
}

const UNIT_API_FIELDS: Record<string, UnitField> = {
  serial: 'serial',
  status: 'status',
  calibration_interval_days: 'interval',
  last_calibrated_at: 'lastCalibrated',
  notes: 'notes',
}

export function unitProblem (error: ApiError, typed: Pick<UnitValues, 'serial'>): SaveProblem<UnitField> {
  if (error.code === 'version_conflict') {
    return { kind: 'stale' }
  }
  if (error.code === 'serial_taken') {
    return {
      kind: 'fields',
      errors: { serial: `${typed.serial.trim()} is already registered for this model.` },
      message: null,
    }
  }
  const errors: Errors<UnitField> = {}
  for (const [field, message] of Object.entries(error.fieldErrors())) {
    const key = UNIT_API_FIELDS[field]
    if (key) {
      errors[key] = message
    }
  }
  if (Object.keys(errors).length > 0) {
    return { kind: 'fields', errors, message: null }
  }
  return error.status === 422 || error.status === 409
    ? { kind: 'fields', errors: {}, message: error.detail }
    : { kind: 'other', message: 'We couldn’t save the unit. Try again in a moment.' }
}

export { normalizeParameter, PARAMETER_MAX } from '@/features/stations/stationFormModel'

// --- Photos staged in the model form ----------------------------------------------------------

/** Photos that can be attached while adding or editing a model (more go in from the gallery). */
export const MAX_STAGED_PHOTOS = 5
/** A phone's photo is a few MB; this keeps the gallery quick without a resize step. */
export const PHOTO_MAX_BYTES = 10 * 1024 * 1024
const PHOTO_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg'])

/** Why this picture can't be attached, in words for the person; null when it can. */
export function photoProblem (file: { name: string, size: number }, staged: readonly { name: string, size: number }[]): string | null {
  const dot = file.name.lastIndexOf('.')
  const ext = dot <= 0 ? '' : file.name.slice(dot).toLowerCase()
  if (!PHOTO_EXTENSIONS.has(ext)) {
    return `${file.name} isn’t a PNG or JPEG picture.`
  }
  if (file.size === 0) {
    return `${file.name} is empty.`
  }
  if (file.size > PHOTO_MAX_BYTES) {
    return `${file.name} is over 10 MB. Choose a smaller picture.`
  }
  if (staged.some(s => s.name === file.name && s.size === file.size)) {
    return `${file.name} is already attached.`
  }
  if (staged.length >= MAX_STAGED_PHOTOS) {
    return `Attach at most ${MAX_STAGED_PHOTOS} photos here. Add more from the model’s page.`
  }
  return null
}
