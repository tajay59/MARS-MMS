import type { StationSummary } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { boundsOf, clusterSize, hasPosition, markerLabel, markerSvg } from '../map'

function station (patch: Partial<StationSummary> = {}): StationSummary {
  return {
    id: 'a', code: 'JM-KIN-001', name: 'Kingston Harbour', type: null, status: 'operational', owner_org_id: 'o',
    owner_org_name: 'Org', country: 'JM', time_zone: 'America/Jamaica', region: null, parameters: [],
    latitude: 17.97, longitude: -76.78, ...patch,
  }
}

describe('hasPosition', () => {
  it('needs both coordinates, as numbers', () => {
    expect(hasPosition(station())).toBe(true)
    expect(hasPosition(station({ latitude: null }))).toBe(false)
    expect(hasPosition(station({ longitude: null }))).toBe(false)
    expect(hasPosition(station({ latitude: 0, longitude: 0 }))).toBe(true) // the equator is a place
    expect(hasPosition(station({ latitude: Number.NaN }))).toBe(false)
  })
})

describe('markerSvg', () => {
  it('draws one shape per status, so status never rests on colour alone', () => {
    const shapes = (['operational', 'degraded', 'offline', 'decommissioned'] as const).map(s => markerSvg(s))
    expect(shapes[0]).toContain('<circle')
    expect(shapes[1]).toContain('<path d="M14 3L26 24H2L14 3z"')
    expect(shapes[2]).toContain('<rect')
    expect(shapes[3]).toContain('fill="#fff"')
    expect(new Set(shapes).size).toBe(4)
  })

  it('takes its colour from the status token', () => {
    expect(markerSvg('offline')).toContain('text-station-offline')
    expect(markerSvg('operational')).toContain('text-station-operational')
  })

  it('shows a status the app does not know as decommissioned, and sizes the picture', () => {
    expect(markerSvg('mystery')).toBe(markerSvg('decommissioned'))
    expect(markerSvg('operational', 36)).toContain('width="36"')
  })
})

describe('clusterSize', () => {
  it('grows with the count', () => {
    expect([2, 5, 10, 99, 100].map(n => clusterSize(n))).toEqual([34, 40, 46, 46, 52])
  })
})

describe('markerLabel', () => {
  it('names the station, its code and its status in words', () => {
    expect(markerLabel(station({ status: 'degraded' }))).toBe('Kingston Harbour, JM-KIN-001, Degraded')
  })
})

describe('boundsOf', () => {
  it('is null for no stations', () => {
    expect(boundsOf([])).toBeNull()
  })

  it('wraps the stations', () => {
    const a = station({ latitude: 17.9, longitude: -76.8 }) as never
    const b = station({ latitude: 18.4, longitude: -77.9 }) as never
    expect(boundsOf([a, b])).toEqual([[17.9, -77.9], [18.4, -76.8]])
  })
})
