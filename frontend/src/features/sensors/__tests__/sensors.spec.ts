import type { SensorModelOut } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { inKind, matchesModel, modelLine, sensorFiltersFrom, sensorQueryFrom, whereLabel } from '../sensors'

function model (patch: Partial<SensorModelOut> = {}): SensorModelOut {
  return {
    id: 'm1',
    kind: 'sensor',
    manufacturer: 'Vaisala',
    model: 'HMP155',
    parameters: ['AT', 'RH'],
    default_calibration_interval_days: 365,
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...patch,
  }
}

describe('filters', () => {
  it('reads them from the URL and ignores a kind it does not know', () => {
    expect(sensorFiltersFrom({ q: ' hmp ', kind: 'logger' })).toEqual({ q: 'hmp', kind: 'logger' })
    expect(sensorFiltersFrom({ kind: 'nonsense' })).toEqual({ q: '', kind: 'all' })
    expect(sensorFiltersFrom({})).toEqual({ q: '', kind: 'all' })
  })

  it('leaves the empty ones out of the URL', () => {
    expect(sensorQueryFrom({ q: '', kind: 'all' })).toEqual({ q: undefined, kind: undefined })
    expect(sensorQueryFrom({ q: 'rv', kind: 'modem' })).toEqual({ q: 'rv', kind: 'modem' })
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
