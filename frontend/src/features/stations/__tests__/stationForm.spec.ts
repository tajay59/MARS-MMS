import type { StationDetail } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/problem'
import {
  createBody,
  emptyValues,
  isUnchanged,
  normalizeParameter,
  onlyZone,
  parseNumber,
  patchBody,
  problemOf,
  validate,
  valuesOf,
} from '../stationFormModel'

// The stations here are made up: the repo is public.
function station (patch: Partial<StationDetail> = {}): StationDetail {
  return {
    id: 'st-1',
    code: 'JM-KIN-001',
    name: 'Kingston Harbour',
    external_id: null,
    status: 'operational',
    owner_org_id: 'org-a',
    owner_org_name: 'Organization A',
    country: 'JM',
    time_zone: 'America/Jamaica',
    type: 'Synoptic',
    region: null,
    parameters: ['AT', 'RH'],
    latitude: 17.9712,
    longitude: -76.7936,
    elevation_m: 6,
    logger: { model: 'CR1000X', serial: null, firmware: null },
    comms: null,
    power: { panel_w: 20, battery_ah: 12, controller: null },
    install_date: '2026-03-14',
    access_notes: null,
    photos: [],
    qr_token: 'token',
    current_config_version: null,
    installed: [],
    version: 3,
    created_at: '2026-03-14T00:00:00Z',
    updated_at: '2026-03-14T00:00:00Z',
    next_calibration_due_at: null,
    last_visit_at: null,
    ...patch,
  } as StationDetail
}

function filled () {
  return {
    ...emptyValues(),
    code: 'JM-KIN-002',
    name: 'Kingston North',
    ownerOrgId: 'org-a',
    country: 'JM',
    timeZone: 'America/Jamaica',
    latitude: '17.98',
    longitude: '-76.8',
  }
}

describe('parsing', () => {
  it('reads decimals, with a comma too, and tells an empty field from a wrong one', () => {
    expect(parseNumber('17.98')).toBe(17.98)
    expect(parseNumber(' -76,8 ')).toBe(-76.8)
    expect(parseNumber('')).toBeNull()
    expect(parseNumber('12abc')).toBeNaN()
    expect(parseNumber('1e5')).toBeNaN()
  })

  it('writes parameter codes the way the server stores them', () => {
    expect(normalizeParameter(' soil_t ')).toBe('SOIL_T')
  })

  it('fills the time zone only for a country with exactly one', () => {
    const zones = { JM: ['America/Jamaica'], US: ['America/New_York', 'America/Chicago'] }
    expect(onlyZone('JM', zones)).toBe('America/Jamaica')
    expect(onlyZone('US', zones)).toBeNull()
    expect(onlyZone('XX', zones)).toBeNull()
  })
})

describe('validate', () => {
  it('accepts a complete new station', () => {
    expect(validate(filled(), 'new')).toEqual({})
  })

  it('asks for what a new station needs', () => {
    const errors = validate(emptyValues(), 'new')
    expect(new Set(Object.keys(errors))).toEqual(
      new Set(['code', 'country', 'latitude', 'longitude', 'name', 'ownerOrgId', 'timeZone']),
    )
  })

  it('keeps latitude and longitude together', () => {
    expect(validate({ ...filled(), longitude: '' }, 'new').longitude).toBe('Add the longitude too')
    expect(validate({ ...filled(), latitude: '91' }, 'new').latitude).toBe('Use a number from -90 to 90')
    expect(validate({ ...filled(), longitude: 'east' }, 'new').longitude).toBe('Use a number from -180 to 180')
  })

  it('lets a station that never had a location stay without one, but not lose it', () => {
    const none = { ...valuesOf(station()), latitude: '', longitude: '' }
    expect(validate(none, 'edit', false)).toEqual({})
    expect(validate(none, 'edit', true).latitude).toBeDefined()
  })

  it('does not ask for the owner when editing: it never changes (B5)', () => {
    expect(validate({ ...filled(), ownerOrgId: '' }, 'edit').ownerOrgId).toBeUndefined()
  })

  it('checks parameters, external IDs and numbers the way the server does', () => {
    expect(validate({ ...filled(), parameters: ['AT', '9X'] }, 'new').parameters).toBeDefined()
    expect(validate({ ...filled(), parameters: Array.from({ length: 41 }, (_, i) => `P${i}`) }, 'new').parameters).toContain('at most 40')
    expect(validate({ ...filled(), externalId: 'has space' }, 'new').externalId).toBeDefined()
    expect(validate({ ...filled(), elevation: '9001' }, 'new').elevation).toBeDefined()
    expect(validate({ ...filled(), panelW: '-1' }, 'new').panelW).toBeDefined()
    expect(validate({ ...filled(), code: 'A' }, 'new').code).toBeDefined()
  })
})

describe('bodies', () => {
  it('builds a create body with blanks as null and groups only when something is in them', () => {
    const body = createBody({ ...filled(), parameters: ['AT'], loggerModel: ' CR1000X ', panelW: '20' })
    expect(body).toMatchObject({
      code: 'JM-KIN-002',
      owner_org_id: 'org-a',
      latitude: 17.98,
      longitude: -76.8,
      external_id: null,
      type: null,
      elevation_m: null,
      parameters: ['AT'],
      logger: { model: 'CR1000X', serial: null, firmware: null },
      comms: null,
      power: { panel_w: 20, battery_ah: null, controller: null },
      status: 'operational',
    })
  })

  it('sends only what changed when editing', () => {
    const original = station()
    const values = { ...valuesOf(original), name: 'Kingston Harbour East', parameters: ['RH', 'AT', 'WS'] }
    expect(patchBody(values, original)).toEqual({ name: 'Kingston Harbour East', parameters: ['RH', 'AT', 'WS'] })
  })

  it('sends both coordinates when either changes, and nothing when neither does', () => {
    const original = station()
    expect(patchBody({ ...valuesOf(original), latitude: '18' }, original)).toEqual({ latitude: 18, longitude: -76.7936 })
    expect(patchBody(valuesOf(original), original)).toEqual({})
    expect(isUnchanged(valuesOf(original), original)).toBe(true)
  })

  it('treats a reordered parameter list as no change, and emptied text as null', () => {
    const original = station({ region: 'Kingston' })
    const values = { ...valuesOf(original), parameters: ['RH', 'AT'], region: '  ' }
    expect(patchBody(values, original)).toEqual({ region: null })
  })

  it('replaces a group only when one of its fields changed', () => {
    const original = station()
    const values = { ...valuesOf(original), loggerSerial: 'LS-1' }
    expect(patchBody(values, original)).toEqual({ logger: { model: 'CR1000X', serial: 'LS-1', firmware: null } })
  })
})

describe('problemOf', () => {
  const error = (status: number, body: Record<string, unknown>) => new ApiError(status, body)

  it('names the field of a duplicate code or external ID', () => {
    expect(problemOf(error(409, { code: 'code_taken' }))).toMatchObject({ kind: 'fields', errors: { code: expect.any(String) } })
    expect(problemOf(error(409, { code: 'external_id_taken' }))).toMatchObject({ kind: 'fields', errors: { externalId: expect.any(String) } })
  })

  it('tells a stale version from the rest', () => {
    expect(problemOf(error(409, { code: 'version_conflict' }))).toEqual({ kind: 'stale' })
  })

  it('maps the server’s field errors onto the form’s', () => {
    const found = problemOf(error(422, {
      code: 'validation_failed',
      detail: 'Validation failed',
      errors: [{ loc: ['body', 'time_zone'], msg: 'Use an IANA time zone' }],
    }))
    expect(found).toMatchObject({ kind: 'fields', errors: { timeZone: 'Use an IANA time zone' } })
  })

  it('keeps a server message with no field, and hides a server fault behind a plain one', () => {
    expect(problemOf(error(422, { code: 'invalid_location', detail: 'Latitude or longitude is out of range' })))
      .toEqual({ kind: 'fields', errors: {}, message: 'Latitude or longitude is out of range' })
    expect(problemOf(error(500, { detail: 'boom' }))).toMatchObject({ kind: 'other' })
  })
})
