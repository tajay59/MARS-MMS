import type { SensorModelOut, SensorUnitOut } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { calibrationSentence, compliance, firstToShow, inKind, kindCounts, matchesModel, matchesReviewUnit, modelLine, reviewLine, sensorFiltersFrom, sensorQueryFrom, specHint, unitBreakdown, unitsRegistered, whereLabel } from '../sensors'

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
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...patch,
  }
}

describe('filters', () => {
  it('reads them from the URL and ignores a kind it does not know', () => {
    expect(sensorFiltersFrom({ q: ' hmp ', kind: 'logger' })).toEqual({ q: 'hmp', kind: 'logger', review: false })
    expect(sensorFiltersFrom({ kind: 'nonsense' })).toEqual({ q: '', kind: 'all', review: false })
    expect(sensorFiltersFrom({})).toEqual({ q: '', kind: 'all', review: false })
    expect(sensorFiltersFrom({ review: '1' }).review).toBe(true)
    expect(sensorFiltersFrom({ review: 'yes' }).review).toBe(false)
  })

  it('leaves the empty ones out of the URL', () => {
    expect(sensorQueryFrom({ q: '', kind: 'all', review: false })).toEqual({ q: undefined, kind: undefined, review: undefined })
    expect(sensorQueryFrom({ q: 'rv', kind: 'modem', review: true })).toEqual({ q: 'rv', kind: 'modem', review: '1' })
  })

  it('groups batteries and solar panels under Power', () => {
    expect(inKind(model({ kind: 'battery' }), 'power')).toBe(true)
    expect(inKind(model({ kind: 'solar_panel' }), 'power')).toBe(true)
    expect(inKind(model({ kind: 'sensor' }), 'power')).toBe(false)
    expect(inKind(model({ kind: 'other' }), 'all')).toBe(true)
  })

  it('searches make, model and parameter', () => {
    const m = model()
    expect(matchesModel(m, { q: 'vais', kind: 'all' })).toBe(true)
    expect(matchesModel(m, { q: 'hmp', kind: 'all' })).toBe(true)
    expect(matchesModel(m, { q: 'rh', kind: 'all' })).toBe(true)
    expect(matchesModel(m, { q: 'campbell', kind: 'all' })).toBe(false)
    expect(matchesModel(m, { q: '', kind: 'logger' })).toBe(false)
  })
})

describe('labels', () => {
  it('describes a model by its kind and what it measures', () => {
    expect(modelLine(model())).toBe('Sensor · AT, RH')
    expect(modelLine(model({ kind: 'logger', parameters: [] }))).toBe('Logger')
  })

  it('says where a unit is', () => {
    expect(whereLabel({ status: 'installed', station: { name: 'Kingston Harbour' }, parameter: 'AT' })).toBe('Kingston Harbour · AT')
    expect(whereLabel({ status: 'installed', station: { name: 'Piarco' }, parameter: null })).toBe('Piarco')
    expect(whereLabel({ status: 'in_stock', station: null, parameter: null })).toBe('Store')
    expect(whereLabel({ status: 'in_repair', station: null, parameter: null })).toBe('Lab')
    expect(whereLabel({ status: 'retired', station: null, parameter: null })).toBe('—')
  })
})

describe('the catalogue list', () => {
  it('counts the units and says what state they are in', () => {
    expect(unitsRegistered({})).toBe('No units yet')
    expect(unitsRegistered({ installed: 1 })).toBe('1 unit registered')
    expect(unitsRegistered({ installed: 1, in_stock: 1, in_repair: 1 })).toBe('3 units registered')
    expect(unitBreakdown({ in_repair: 1, installed: 2, retired: 0 })).toEqual([
      { status: 'installed', text: '2 installed' },
      { status: 'in_repair', text: '1 in repair' },
    ])
  })

  it('counts models for each filter chip', () => {
    const list = [model(), model({ kind: 'logger' }), model({ kind: 'battery' }), model({ kind: 'solar_panel' })]
    expect(kindCounts(list)).toEqual({ all: 4, sensor: 1, logger: 1, modem: 0, power: 2 })
  })

  it('hints with the first specification, if there is one', () => {
    expect(specHint(model())).toBeNull()
    expect(specHint(model({ specs: [{ label: 'Range', value: '500-1100 hPa', detail: null }] }))).toBe('500-1100 hPa')
  })
})

describe('calibration of the units', () => {
  const unit = (due_state: string | null, status = 'installed') => ({ due_state, status }) as Parameters<typeof firstToShow>[0][number]

  it('measures how many are within calibration, leaving out units with no interval', () => {
    expect(compliance([])).toBeNull()
    expect(compliance([unit(null)])).toBeNull()
    expect(compliance([unit('ok'), unit('due_soon'), unit('overdue'), unit(null)])).toEqual({ ok: 2, of: 3, percent: 66.7 })
  })

  it('starts the status bar on the unit that needs attention', () => {
    const list = [unit('ok'), unit('due_soon'), unit('overdue')]
    expect(firstToShow(list)).toBe(list[2])
    expect(firstToShow([unit('ok', 'in_stock'), unit('ok')])?.status).toBe('installed')
    expect(firstToShow([])).toBeNull()
  })

  it('writes the last and the next calibration in a sentence', () => {
    const now = new Date('2026-10-20T12:00:00Z')
    expect(calibrationSentence({ last_calibrated_at: null, last_calibration_result: null, calibration_due_at: null }, now))
      .toBe('Not calibrated yet. No calibration interval is set.')
    expect(calibrationSentence({ last_calibrated_at: '2026-03-12T00:00:00Z', last_calibration_result: 'pass', calibration_due_at: '2026-12-01T12:00:00Z' }, now))
      .toMatch(/^Last calibrated .*2026 · Pass\. Next due .*2026 \(in 42 days\)\.$/)
    expect(calibrationSentence({ last_calibrated_at: null, last_calibration_result: null, calibration_due_at: '2026-10-19T12:00:00Z' }, now))
      .toMatch(/\(1 day overdue\)\.$/)
  })
})

describe('units waiting for a check', () => {
  const unit = {
    id: 'u1', serial: 'V-23044', parameter: 'AT', status: 'installed', needs_review: true,
    model: { id: 'm1', kind: 'sensor', manufacturer: 'Vaisala', model: 'HMP155' },
    station: { id: 's1', name: 'Kingston Harbour', code: 'JM-KIN-001' },
  } as SensorUnitOut

  it('reads as the model and what it measures', () => {
    expect(reviewLine(unit)).toBe('Vaisala HMP155 · AT')
    expect(reviewLine({ ...unit, parameter: null })).toBe('Vaisala HMP155')
  })

  it('is found by serial, model, parameter or station', () => {
    expect(matchesReviewUnit(unit, '')).toBe(true)
    expect(matchesReviewUnit(unit, ' v-230 ')).toBe(true)
    expect(matchesReviewUnit(unit, 'hmp')).toBe(true)
    expect(matchesReviewUnit(unit, 'harbour')).toBe(true)
    expect(matchesReviewUnit(unit, 'jm-kin')).toBe(true)
    expect(matchesReviewUnit(unit, 'campbell')).toBe(false)
    expect(matchesReviewUnit({ ...unit, station: null }, 'harbour')).toBe(false)
  })
})
