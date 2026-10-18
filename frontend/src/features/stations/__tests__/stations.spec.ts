import type { InstalledUnit, StationSummary } from '@/api/models'
import { describe, expect, it } from 'vitest'
import {
  dueLabel,
  dueState,
  extraFilterCount,
  facetsOf,
  filtersFrom,
  lookOf,
  matches,
  matchesOthers,
  queryFrom,
  sortInstalled,
  sortParameters,
  splitParameters,
} from '../stations'

// The stations here are made up: the repo is public.
function station (patch: Partial<StationSummary> = {}): StationSummary {
  return {
    id: 'st-1',
    code: 'JM-KIN-001',
    name: 'Kingston Harbour',
    external_id: 'DEV0000000000000000000000000000001',
    status: 'operational',
    owner_org_id: 'org-a',
    owner_org_name: 'Organization A',
    country: 'JM',
    time_zone: 'America/Jamaica',
    type: 'Synoptic',
    region: null,
    latitude: 17.97,
    longitude: -76.79,
    parameters: ['RH', 'AT', 'RAIN'],
    next_calibration_due_at: null,
    last_visit_at: null,
    ...patch,
  }
}

function unit (patch: Partial<InstalledUnit> & { kind?: string } = {}): InstalledUnit {
  const { kind = 'sensor', ...rest } = patch
  return {
    unit_id: 'u-1',
    serial: 'S-1',
    parameter: 'AT',
    model: { id: 'm-1', kind, manufacturer: 'Maker', model: 'M1' },
    installed_at: null,
    last_calibrated_at: null,
    last_calibration_result: null,
    calibration_due_at: null,
    due_state: null,
    flags: [],
    needs_review: false,
    ...rest,
  } as InstalledUnit
}

const NONE = { q: '', status: null, org: null, country: null, type: null, parameter: null }

describe('calibration due (CAL-4)', () => {
  const now = new Date('2026-10-18T12:00:00Z')

  it('is overdue, due within 30 days, or in date', () => {
    expect(dueState('2026-10-01T00:00:00Z', now)).toBe('overdue')
    expect(dueState('2026-11-10T00:00:00Z', now)).toBe('due_soon')
    expect(dueState('2026-12-31T00:00:00Z', now)).toBe('ok')
  })

  it('has no state without a due date', () => {
    expect(dueState(null, now)).toBeNull()
    expect(dueState('not a date', now)).toBeNull()
  })

  it('says it in words, on the station’s calendar', () => {
    expect(dueLabel('overdue', '2026-02-14T12:00:00Z', 'America/Jamaica', now)).toBe('Overdue since 14 Feb')
    expect(dueLabel('due_soon', '2026-11-05T12:00:00Z', 'America/Jamaica', now)).toBe('Due 5 Nov')
    expect(dueLabel('ok', '2027-01-01T00:00:00Z', null, now)).toBe('In date')
    expect(dueLabel(null, null, null, now)).toBe('No interval')
    // 03:00 UTC on 1 Mar is still 28 Feb in Jamaica
    expect(dueLabel('overdue', '2026-03-01T03:00:00Z', 'America/Jamaica', now)).toBe('Overdue since 28 Feb')
  })
})

describe('station status', () => {
  it('shows an unknown status as grey, never as a colour of its own', () => {
    expect(lookOf('offline').label).toBe('Offline')
    expect(lookOf('something new').label).toBe('Decommissioned')
  })
})

describe('filters in the URL', () => {
  it('read one value per filter and ignore an unknown status', () => {
    expect(filtersFrom({ q: '  kin ', status: 'sleeping', parameter: 'rain', org: ['org-a', 'org-b'] }))
      .toEqual({ ...NONE, q: 'kin', parameter: 'RAIN', org: 'org-a' })
  })

  it('round-trip, leaving out the empty ones', () => {
    const filters = { ...NONE, status: 'degraded' as const, country: 'JM' }
    expect(queryFrom(filters)).toEqual({
      q: undefined, status: 'degraded', org: undefined, country: 'JM', type: undefined, parameter: undefined,
    })
    expect(filtersFrom(queryFrom(filters) as Record<string, string>)).toEqual(filters)
  })

  it('count the filters the phone keeps in its sheet', () => {
    expect(extraFilterCount({ ...NONE, q: 'x', status: 'offline' })).toBe(0)
    expect(extraFilterCount({ ...NONE, org: 'org-a', parameter: 'AT' })).toBe(2)
  })
})

describe('matching', () => {
  it('searches the code, the name and the external ID (W5-8)', () => {
    const s = station()
    expect(matches(s, { ...NONE, q: 'kin-0' })).toBe(true)
    expect(matches(s, { ...NONE, q: 'HARBOUR' })).toBe(true)
    expect(matches(s, { ...NONE, q: '0000001' })).toBe(true)
    expect(matches(s, { ...NONE, q: 'montego' })).toBe(false)
    expect(matches(station({ external_id: null }), { ...NONE, q: 'kin' })).toBe(true)
  })

  it('applies every filter together', () => {
    const s = station()
    expect(matches(s, { ...NONE, org: 'org-a', country: 'JM', type: 'Synoptic', parameter: 'RAIN' })).toBe(true)
    expect(matches(s, { ...NONE, org: 'org-b' })).toBe(false)
    expect(matches(s, { ...NONE, parameter: 'WS' })).toBe(false)
    expect(matches(s, { ...NONE, status: 'offline' })).toBe(false)
  })

  it('leaves status out of the counts the status buttons show', () => {
    expect(matchesOthers(station(), { ...NONE, status: 'offline' })).toBe(true)
  })
})

describe('facets', () => {
  it('offer what the visible stations have, sorted', () => {
    const facets = facetsOf([
      station({ owner_org_id: 'org-b', owner_org_name: 'Organization B', country: 'TT', type: null, parameters: ['WS', 'PM10'] }),
      station(),
    ])
    expect(facets.orgs).toEqual([{ value: 'org-a', title: 'Organization A' }, { value: 'org-b', title: 'Organization B' }])
    expect(facets.countries).toEqual(['JM', 'TT'])
    expect(facets.types).toEqual(['Synoptic'])
    expect(facets.parameters).toEqual(['AT', 'RH', 'RAIN', 'WS', 'PM10'])
  })
})

describe('parameters', () => {
  it('put the common ones first, in reading order, then the rest A–Z', () => {
    expect(sortParameters(['ZZ', 'RAIN', 'BV', 'AT'])).toEqual(['AT', 'RAIN', 'BV', 'ZZ'])
  })

  it('split into chips and a searchable field', () => {
    expect(splitParameters(['PM10', 'RH', 'BV', 'AT'])).toEqual({ common: ['AT', 'RH'], other: ['BV', 'PM10'] })
    expect(splitParameters(['BV'])).toEqual({ common: [], other: ['BV'] })
  })
})

describe('installed units', () => {
  it('list sensors by parameter, then the other parts by kind and serial', () => {
    const sorted = sortInstalled([
      unit({ unit_id: 'battery', parameter: null, kind: 'battery', serial: 'B-2' }),
      unit({ unit_id: 'rain', parameter: 'RAIN' }),
      unit({ unit_id: 'logger', parameter: null, kind: 'logger', serial: 'L-1' }),
      unit({ unit_id: 'at', parameter: 'AT' }),
    ])
    expect(sorted.map(u => u.unit_id)).toEqual(['at', 'rain', 'logger', 'battery'])
  })
})
