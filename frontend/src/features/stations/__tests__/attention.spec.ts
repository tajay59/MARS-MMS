import type { RequestSummary, StationSummary, VisitOut } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { attentionRows, emptyWork, nextStep, problemCounts, problemFrom, problemsOf, viewFrom, workFrom } from '../attention'

const NOW = new Date('2026-11-19T15:00:00Z')

function station (over: Partial<StationSummary> = {}): StationSummary {
  return {
    id: 's1', code: 'JM-KIN-001', name: 'Liguanea Plain', status: 'operational', country: 'JM',
    time_zone: 'America/Jamaica', owner_org_id: 'o1', owner_org_name: 'Org A', external_id: null,
    latitude: 18, longitude: -76.8, parameters: [], region: null, type: null,
    last_visit_at: '2026-11-02T14:00:00Z', next_calibration_due_at: '2027-03-30T05:00:00Z', ...over,
  } as StationSummary
}

function visit (over: Partial<VisitOut>, stationIds: string[]): VisitOut {
  return {
    id: 'v1', ref: 'VR-2026-0081', status: 'planned', planned_start: '2026-11-21T13:00:00Z',
    stations: stationIds.map(id => ({ station_id: id, time_zone: 'America/Jamaica' })), ...over,
  } as unknown as VisitOut
}

function request (over: Partial<RequestSummary>, stationIds: string[]): RequestSummary {
  return {
    id: 'r1', ref: 'MR-2026-0112', status: 'assigned', updated_at: '2026-11-15T10:00:00Z',
    stations: stationIds.map(id => ({ id, code: 'X', name: 'X', country: 'JM' })), ...over,
  } as unknown as RequestSummary
}

describe('what is wrong with a station', () => {
  it('lists every problem, worst first, and nothing for a decommissioned one', () => {
    const s = station({ status: 'offline', next_calibration_due_at: '2026-10-09T04:00:00Z', last_visit_at: '2026-07-01T12:00:00Z' })
    expect(problemsOf(s, NOW)).toEqual(['offline', 'overdue', 'idle'])
    expect(problemsOf({ ...s, status: 'decommissioned' }, NOW)).toEqual([])
    expect(problemsOf(station(), NOW)).toEqual([])
  })

  it('does not call a station never visited idle: imported stations have no visits yet', () => {
    expect(problemsOf(station({ last_visit_at: null }), NOW)).toEqual([])
  })

  it('counts each problem across the network, a station in every count it belongs to', () => {
    const counts = problemCounts([
      station({ status: 'offline', next_calibration_due_at: '2026-10-09T04:00:00Z' }),
      station({ id: 's2', status: 'degraded' }),
      station({ id: 's3', last_visit_at: '2026-06-01T12:00:00Z' }),
    ], NOW)
    expect(counts).toEqual({ offline: 1, degraded: 1, overdue: 1, idle: 1 })
  })
})

describe('the open work at a station', () => {
  it('prefers a started visit, then the next planned one, and the request changed last', () => {
    const work = workFrom([
      visit({ id: 'later', planned_start: '2026-11-30T13:00:00Z' }, ['s1']),
      visit({ id: 'sooner' }, ['s1']),
      visit({ id: 'ended', status: 'ended' }, ['s2']),
      visit({ id: 'now', status: 'started', planned_start: '2026-12-01T13:00:00Z' }, ['s3']),
      visit({ id: 'next', planned_start: '2026-11-20T13:00:00Z' }, ['s3']),
    ], [
      request({ id: 'old', updated_at: '2026-11-01T00:00:00Z' }, ['s1']),
      request({ id: 'new' }, ['s1']),
      request({ id: 'closed', status: 'closed', updated_at: '2026-11-18T00:00:00Z' }, ['s1']),
    ])
    expect(work.visits.get('s1')?.id).toBe('sooner')
    expect(work.visits.has('s2')).toBe(false)
    expect(work.visits.get('s3')?.id).toBe('now')
    expect(work.requests.get('s1')?.id).toBe('new')
  })

  it('opens the visit, else the request, else raises one; nothing for viewers and clients', () => {
    const work = workFrom([visit({}, ['s1'])], [request({}, ['s1', 's2'])])
    expect(nextStep('s1', work, true)).toEqual({ kind: 'visit', id: 'v1', label: 'Open the visit' })
    expect(nextStep('s2', work, true)).toEqual({ kind: 'request', id: 'r1', label: 'Open the request' })
    expect(nextStep('s3', work, true)).toEqual({ kind: 'raise', stationId: 's3', label: 'Raise a request' })
    expect(nextStep('s1', work, false)).toBeNull()
  })
})

describe('the Needs attention rows', () => {
  const stations = [
    station({ id: 'idle', code: 'VC-KST-001', last_visit_at: '2026-07-01T12:00:00Z' }),
    station({ id: 'cal', code: 'BB-BGI-001', next_calibration_due_at: '2026-10-09T04:00:00Z', time_zone: 'America/Barbados' }),
    station({ id: 'off-handled', code: 'TT-POS-003', status: 'offline' }),
    station({ id: 'off', code: 'JM-STE-014', status: 'offline', last_visit_at: '2026-09-03T14:00:00Z' }),
    station({ id: 'deg', code: 'JM-MBJ-002', status: 'degraded' }),
    station({ id: 'fine', code: 'JM-KIN-001' }),
  ]
  const work = workFrom([visit({}, ['off-handled'])], [request({}, ['deg'])])

  it('ranks by problem, unhandled first, and says one fact each', () => {
    const rows = attentionRows(stations, work, NOW, true)
    expect(rows.map(r => r.station.id)).toEqual(['off', 'off-handled', 'deg', 'cal', 'idle'])
    expect(rows.map(r => r.fact)).toEqual([
      'Marked offline · last visit 3 Sep',
      'Marked offline · visit planned for 21 Nov',
      'Marked degraded · request open',
      'Calibration 41 days overdue (due 9 Oct)',
      'Last visited 141 days ago (1 Jul)',
    ])
    expect(rows[1]!.workRef).toBe('VR-2026-0081')
    expect(rows.map(r => r.next?.label)).toEqual(['Raise a request', 'Open the visit', 'Open the request', 'Raise a request', 'Raise a request'])
  })

  it('filters to one problem, showing a station under it even when it has a worse one', () => {
    const both = station({ id: 'both', status: 'offline', next_calibration_due_at: '2026-11-01T04:00:00Z' })
    expect(attentionRows([both], emptyWork(), NOW, true, 'overdue').map(r => r.problem)).toEqual(['overdue'])
    expect(attentionRows([both], emptyWork(), NOW, true).map(r => r.problem)).toEqual(['offline'])
  })
})

describe('the page state in the address', () => {
  it('opens on Needs attention, and on All stations when a link brings a filter', () => {
    expect(viewFrom({})).toBe('attention')
    expect(viewFrom({ view: 'all' })).toBe('all')
    expect(viewFrom({ org: 'o1' })).toBe('all')
    expect(viewFrom({ org: 'o1', view: 'attention' })).toBe('attention')
    expect(viewFrom({ q: 'kin' })).toBe('attention')
    expect(problemFrom({ problem: 'overdue' })).toBe('overdue')
    expect(problemFrom({ problem: 'bogus' })).toBeNull()
  })
})
