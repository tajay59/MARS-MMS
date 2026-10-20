import type { StationSummary } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from '@/api/problem'
import { landingStateFor, MAX_SUGGESTIONS, stationRoute, suggestStations, tokenFromScan } from '../scan'

function station (code: string, name = code): StationSummary {
  return {
    id: `id-${code}`, code, name, type: null, status: 'operational', owner_org_id: 'o', owner_org_name: 'Org',
    country: 'JM', time_zone: 'America/Jamaica', region: null, parameters: [], latitude: null, longitude: null,
  }
}

describe('tokenFromScan', () => {
  it('reads the token from a label address', () => {
    expect(tokenFromScan('https://mms.example.org/s/AbC-d_9xYzAbC-d_9xYzAb')).toBe('AbC-d_9xYzAbC-d_9xYzAb')
  })

  it('allows a trailing slash, a query and surrounding spaces', () => {
    expect(tokenFromScan('  https://mms.example.org/s/abc123/?utm=1 ')).toBe('abc123')
  })

  it('does not compare hosts: a label from another environment resolves to "not found"', () => {
    expect(tokenFromScan('https://mms.localhost/s/abc123')).toBe('abc123')
  })

  it.each([
    'JM-KIN-001',
    '',
    'abc123',
    'javascript:alert(1)',
    'https://mms.example.org/stations/abc123',
    'https://mms.example.org/s/',
    'https://mms.example.org/s/a/b',
    'https://mms.example.org/s/has space',
    'https://mms.example.org/s/%E0%A4%A',
    `https://mms.example.org/s/${'a'.repeat(65)}`,
    'ftp://mms.example.org/s/abc',
  ])('rejects %j', text => {
    expect(tokenFromScan(text)).toBeNull()
  })
})

describe('landingStateFor', () => {
  const problem = (status: number) => new ApiError(status, { code: 'x' })

  it('maps the answers to the screens of AFD §5.3', () => {
    expect(landingStateFor(problem(410))).toBe('revoked')
    expect(landingStateFor(problem(404))).toBe('missing')
    expect(landingStateFor(problem(422))).toBe('missing')
    expect(landingStateFor(new NetworkError(new Error('x')))).toBe('offline')
    expect(landingStateFor(problem(500))).toBe('failed')
    expect(landingStateFor(new Error('boom'))).toBe('failed')
  })
})

describe('stationRoute', () => {
  it('opens the station for staff and clients alike', () => {
    expect(stationRoute({ station_id: 'abc', code: 'C', name: 'N', view: 'client' })).toEqual({ name: 'stations', params: { id: 'abc' } })
  })
})

describe('suggestStations', () => {
  const all = [station('JM-KIN-002'), station('JM-KIN-001'), station('JM-MOB-001'), station('TT-KIN-009')]

  it('lists codes that start with the text first, sorted', () => {
    expect(suggestStations(all, 'jm-kin').map(s => s.code)).toEqual(['JM-KIN-001', 'JM-KIN-002'])
    expect(suggestStations(all, 'kin').map(s => s.code)).toEqual(['JM-KIN-001', 'JM-KIN-002', 'TT-KIN-009'])
  })

  it('ignores case and spaces', () => {
    expect(suggestStations(all, ' jm - mob ').map(s => s.code)).toEqual(['JM-MOB-001'])
    expect(suggestStations(all, 'JM-MOB').map(s => s.code)).toEqual(['JM-MOB-001'])
  })

  it('shows nothing for an empty field, and at most eight rows', () => {
    expect(suggestStations(all, '  ')).toEqual([])
    const many = Array.from({ length: 20 }, (_, i) => station(`AA-${String(i).padStart(3, '0')}`))
    expect(suggestStations(many, 'aa')).toHaveLength(MAX_SUGGESTIONS)
  })

  it('does not change the list it is given', () => {
    const before = all.map(s => s.code)
    suggestStations(all, 'kin')
    expect(all.map(s => s.code)).toEqual(before)
  })
})
