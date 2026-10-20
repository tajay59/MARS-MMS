import type { SensorModelOut, SensorUnitOut } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/problem'
import {
  emptyModel,
  emptyUnit,
  localToday,
  modelCreateBody,
  modelPatchBody,
  modelProblem,
  modelValues,
  parseDays,
  photoProblem,
  specsBody,
  unitCreateBody,
  unitPatchBody,
  unitProblem,
  unitValues,
  validateModel,
  validateUnit,
} from '../sensorForms'

function model (patch: Partial<SensorModelOut> = {}): SensorModelOut {
  return {
    id: 'm1',
    kind: 'sensor',
    manufacturer: 'Vaisala',
    model: 'HMP155',
    parameters: ['AT', 'RH'],
    default_calibration_interval_days: 365,
    specs: [],
    unit_counts: {},
    photo_count: 0,
    cover_document_id: null,
    version: 3,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...patch,
  }
}

function unit (patch: Partial<SensorUnitOut> = {}): SensorUnitOut {
  return {
    id: 'u1',
    serial: 'V-23001',
    status: 'in_stock',
    model: { id: 'm1', kind: 'sensor', manufacturer: 'Vaisala', model: 'HMP155', parameters: ['AT'] },
    station: null,
    parameter: null,
    calibration_interval_days: null,
    effective_interval_days: 365,
    last_calibrated_at: null,
    last_calibration_result: null,
    calibration_due_at: null,
    due_state: null,
    needs_review: false,
    flags: [],
    notes: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    version: 5,
    ...patch,
  } as SensorUnitOut
}

function problem (status: number, code: string, extra: Record<string, unknown> = {}): ApiError {
  return new ApiError(status, { code, detail: 'The server says no', ...extra })
}

describe('parseDays', () => {
  it('reads whole days, nothing as null, and anything else as NaN', () => {
    expect(parseDays(' 180 ')).toBe(180)
    expect(parseDays('')).toBeNull()
    expect(parseDays('  ')).toBeNull()
    expect(parseDays('1.5')).toBeNaN()
    expect(parseDays('-3')).toBeNaN()
    expect(parseDays('a')).toBeNaN()
  })
})

describe('model form', () => {
  it('asks for a make and a model', () => {
    expect(validateModel(emptyModel())).toEqual({ manufacturer: 'Enter the make', model: 'Enter the model' })
  })

  it('checks the interval and the parameter codes', () => {
    const v = { ...emptyModel(), manufacturer: 'A', model: 'B' }
    expect(validateModel({ ...v, interval: '0' }).interval).toMatch(/1 to 3650/)
    expect(validateModel({ ...v, interval: '3651' }).interval).toMatch(/1 to 3650/)
    expect(validateModel({ ...v, interval: '365' })).toEqual({})
    expect(validateModel({ ...v, parameters: ['AT', '9X'] }).parameters).toMatch(/Start each code with a letter/)
    expect(validateModel({ ...v, parameters: Array.from({ length: 21 }, (_, i) => `P${i}`) }).parameters).toBe('Use at most 20 parameters')
  })

  it('builds the create body from typed text', () => {
    const v = { ...emptyModel(), manufacturer: ' Vaisala ', model: 'HMP155 ', parameters: ['AT'], interval: '365' }
    expect(modelCreateBody(v)).toEqual({
      kind: 'sensor',
      manufacturer: 'Vaisala',
      model: 'HMP155',
      parameters: ['AT'],
      default_calibration_interval_days: 365,
      specs: [],
    })
    expect(modelCreateBody({ ...v, interval: '' }).default_calibration_interval_days).toBeNull()
  })

  it('sends only what changed, with the version', () => {
    const was = model()
    expect(modelPatchBody(modelValues(was), was)).toBeNull()
    expect(modelPatchBody({ ...modelValues(was), model: 'HMP110' }, was)).toEqual({ version: 3, model: 'HMP110' })
    expect(modelPatchBody({ ...modelValues(was), parameters: ['AT'] }, was)).toEqual({ version: 3, parameters: ['AT'] })
    // Clearing the interval sends null: the model has no fixed interval
    expect(modelPatchBody({ ...modelValues(was), interval: '' }, was)).toEqual({ version: 3, default_calibration_interval_days: null })
  })

  it('says what a failed save means', () => {
    const typed = { manufacturer: 'Vaisala', model: 'HMP110' }
    expect(modelProblem(problem(409, 'version_conflict'), typed)).toEqual({ kind: 'stale' })
    expect(modelProblem(problem(409, 'model_taken'), typed)).toEqual({
      kind: 'fields',
      errors: { model: 'Vaisala HMP110 is already in the catalogue.' },
      message: null,
    })
    const invalid = problem(422, 'validation_error', { errors: [{ loc: ['body', 'default_calibration_interval_days'], msg: 'Too big' }] })
    expect(modelProblem(invalid, typed)).toEqual({ kind: 'fields', errors: { interval: 'Too big' }, message: null })
    expect(modelProblem(problem(500, 'http_error'), typed).kind).toBe('other')
  })
})

describe('unit form', () => {
  const today = '2026-10-19'

  it('asks for a serial', () => {
    expect(validateUnit(emptyUnit(), true, today)).toEqual({ serial: 'Enter the serial number' })
    expect(validateUnit({ ...emptyUnit(), serial: 'x'.repeat(81) }, true, today).serial).toBe('Use at most 80 characters')
  })

  it('checks the last calibration only when adding, and never in the future', () => {
    const v = { ...emptyUnit(), serial: 'V-1', lastCalibrated: '2026-10-20' }
    expect(validateUnit(v, true, today).lastCalibrated).toBe('A calibration can’t be in the future')
    expect(validateUnit({ ...v, lastCalibrated: '2026-10-19' }, true, today)).toEqual({})
    expect(validateUnit({ ...v, lastCalibrated: '2026-13-40' }, true, today).lastCalibrated).toBe('Enter a date')
    expect(validateUnit(v, false, today)).toEqual({})
  })

  it('builds the create body for the page’s model', () => {
    const v = { ...emptyUnit(), serial: ' V-23005 ', interval: '180', lastCalibrated: '2026-03-01', notes: ' ' }
    expect(unitCreateBody(v, 'm1')).toEqual({
      model_id: 'm1',
      serial: 'V-23005',
      status: 'in_stock',
      calibration_interval_days: 180,
      last_calibrated_at: '2026-03-01T00:00:00Z',
      notes: null,
    })
  })

  it('sends only what changed', () => {
    const was = unit({ notes: 'Old mast', calibration_interval_days: 180 })
    expect(unitPatchBody(unitValues(was), was)).toBeNull()
    expect(unitPatchBody({ ...unitValues(was), serial: 'V-9' }, was)).toEqual({ version: 5, serial: 'V-9' })
    expect(unitPatchBody({ ...unitValues(was), status: 'retired' }, was)).toEqual({ version: 5, status: 'retired' })
    expect(unitPatchBody({ ...unitValues(was), needsReview: true }, was)).toEqual({ version: 5, needs_review: true })
    // Clearing the override goes back to the model's interval; clearing the notes sends null
    expect(unitPatchBody({ ...unitValues(was), interval: '', notes: '' }, was)).toEqual({
      version: 5,
      calibration_interval_days: null,
      notes: null,
    })
  })

  it('keeps the status of an installed unit out of the body', () => {
    const installed = unit({ status: 'installed' })
    const v = { ...unitValues(installed), status: 'retired' as const }
    expect(unitPatchBody(v, installed)).toBeNull()
    expect(unitPatchBody({ ...v, serial: 'V-9' }, installed)).toEqual({ version: 5, serial: 'V-9' })
  })

  it('starts an installed unit on a harmless status the form never sends', () => {
    expect(unitValues(unit({ status: 'installed' })).status).toBe('in_stock')
    expect(unitValues(unit({ status: 'in_repair' })).status).toBe('in_repair')
  })

  it('says what a failed save means', () => {
    expect(unitProblem(problem(409, 'version_conflict'), { serial: 'V-1' })).toEqual({ kind: 'stale' })
    expect(unitProblem(problem(409, 'serial_taken'), { serial: ' V-1 ' })).toEqual({
      kind: 'fields',
      errors: { serial: 'V-1 is already registered for this model.' },
      message: null,
    })
    expect(unitProblem(problem(409, 'unit_installed'), { serial: 'V-1' })).toEqual({
      kind: 'fields',
      errors: {},
      message: 'The server says no',
    })
    expect(unitProblem(problem(503, 'http_error'), { serial: 'V-1' }).kind).toBe('other')
  })
})

describe('localToday', () => {
  it('is the device’s date as yyyy-mm-dd', () => {
    expect(localToday(new Date(2026, 9, 5, 23, 59))).toBe('2026-10-05')
  })
})

describe('model specifications', () => {
  const typed = { label: ' Operating range ', value: ' -80 to +60 °C ', detail: ' 0 to 100 % RH ' }

  it('sends a line only when it has a name and a value, trimmed, with an empty second line as null', () => {
    expect(specsBody([typed, { label: 'Accuracy', value: '±0.17 °C', detail: '' }, { label: 'Half', value: '', detail: 'x' }, { label: '', value: '', detail: '' }])).toEqual([
      { label: 'Operating range', value: '-80 to +60 °C', detail: '0 to 100 % RH' },
      { label: 'Accuracy', value: '±0.17 °C', detail: null },
    ])
  })

  it('refuses a half-typed line and more than eight', () => {
    const v = { ...emptyModel(), manufacturer: 'A', model: 'B' }
    expect(validateModel({ ...v, specs: [{ label: 'Range', value: '', detail: '' }] }).specs).toBe('Give each specification a name and a value')
    expect(validateModel({ ...v, specs: Array.from({ length: 9 }, () => typed) }).specs).toBe('Use at most 8 specifications')
    expect(validateModel({ ...v, specs: [typed, { label: '', value: '', detail: '' }] })).toEqual({})
  })

  it('sends specs in a patch only when they changed', () => {
    const was = model({ specs: [{ label: 'Range', value: '0-5 V', detail: null }] })
    expect(modelPatchBody(modelValues(was), was)).toBeNull()
    expect(modelPatchBody({ ...modelValues(was), specs: [] }, was)).toEqual({ version: 3, specs: [] })
    const edited = modelValues(was)
    edited.specs[0]!.value = '0-1 V'
    expect(modelPatchBody(edited, was)).toEqual({ version: 3, specs: [{ label: 'Range', value: '0-1 V', detail: null }] })
  })
})

describe('photos staged in the form', () => {
  const pic = (name: string, size = 1000) => ({ name, size })

  it('takes PNG and JPEG pictures up to 10 MB', () => {
    expect(photoProblem(pic('a.jpg'), [])).toBeNull()
    expect(photoProblem(pic('A.PNG'), [])).toBeNull()
    expect(photoProblem(pic('a.webp'), [])).toMatch(/PNG or JPEG/)
    expect(photoProblem(pic('a.jpg', 0), [])).toMatch(/empty/)
    expect(photoProblem(pic('a.jpg', 10 * 1024 * 1024 + 1), [])).toMatch(/over 10 MB/)
  })

  it('refuses the same picture twice and more than five', () => {
    expect(photoProblem(pic('a.jpg'), [pic('a.jpg')])).toMatch(/already attached/)
    expect(photoProblem(pic('f.jpg'), ['a', 'b', 'c', 'd', 'e'].map(n => pic(`${n}.jpg`)))).toMatch(/at most 5/)
  })
})
