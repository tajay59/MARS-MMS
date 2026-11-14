import type { VisitOut } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from '@/api/problem'
import { failureOf, replaceVisit } from '../failures'
import {
  canDo,
  formatClock,
  formatRange,
  formatWhen,
  isLive,
  lookOfVisit,
  matchesVisit,
  sortVisits,
  stationNames,
  stationTimes,
  utcToZoned,
  validateSchedule,
  visitZone,
  withoutPerson,
  zonedToUtc,
} from '../visits'

const JAMAICA = 'America/Jamaica' // UTC-5 all year, no daylight saving
const EMPTY_BOARD = { note: 0, task: 0, recommendation: 0, config: 0, incomplete_tasks: 0, cover: null }

function visit (patch: Partial<VisitOut> = {}): VisitOut {
  return {
    id: 'v1', ref: 'VR-2026-0042-01', status: 'planned', request_id: 'r1', request_ref: 'MR-2026-0042',
    request_title: 'Rain gauge reads zero', org_id: 'o1',
    planned_start: '2026-10-22T13:00:00Z', planned_end: '2026-10-23T21:00:00Z',
    started_at: null, ended_at: null, additional_visit_required: null, follow_up_notes: null, notes: null,
    lead: { id: 'u1', name: 'Andrea Clarke' },
    staff: [{ id: 'u1', name: 'Andrea Clarke' }, { id: 'u2', name: 'Devon Brown' }],
    stations: [
      { station_id: 's1', station_code: 'JM-KIN-001', station_name: 'Kingston Harbour', time_zone: JAMAICA, owner: { id: 'u1', name: 'Andrea Clarke' }, arrived_at: null, departed_at: null, actions: [], board: EMPTY_BOARD },
      { station_id: 's2', station_code: 'JM-MBJ-002', station_name: 'Montego Bay Airport', time_zone: JAMAICA, owner: { id: 'u2', name: 'Devon Brown' }, arrived_at: null, departed_at: null, actions: [], board: EMPTY_BOARD },
    ],
    actions: [], prepared_on: [], version: 1, ...patch,
  }
}

describe('times in a station\'s zone', () => {
  it('turns a wall-clock time in the zone into the UTC instant', () => {
    expect(zonedToUtc('2026-10-22T08:00', JAMAICA)).toBe('2026-10-22T13:00:00.000Z')
  })

  it('goes back the same way', () => {
    expect(utcToZoned('2026-10-22T13:00:00Z', JAMAICA)).toBe('2026-10-22T08:00')
    expect(utcToZoned(zonedToUtc('2026-01-05T23:30', 'Europe/London')!, 'Europe/London')).toBe('2026-01-05T23:30')
  })

  it('follows a zone that changes its clock', () => {
    // New York is UTC-4 on 1 Oct and UTC-5 on 1 Dec
    expect(zonedToUtc('2026-10-01T08:00', 'America/New_York')).toBe('2026-10-01T12:00:00.000Z')
    expect(zonedToUtc('2026-12-01T08:00', 'America/New_York')).toBe('2026-12-01T13:00:00.000Z')
  })

  it('refuses what is not a date and time', () => {
    expect(zonedToUtc('', JAMAICA)).toBeNull()
    expect(zonedToUtc('22 Oct', JAMAICA)).toBeNull()
  })

  it('writes the day and the time in the zone', () => {
    expect(formatWhen('2026-10-22T13:00:00Z', JAMAICA)).toBe('Thu 22 Oct, 08:00')
    expect(formatClock('2026-10-22T13:12:00Z', JAMAICA)).toBe('08:12')
    expect(formatWhen(null)).toBe('—')
  })

  it('writes a range, and leaves the day out of the end when it is the same', () => {
    expect(formatRange('2026-10-22T13:00:00Z', '2026-10-23T21:00:00Z', JAMAICA)).toBe('Thu 22 Oct, 08:00 to Fri 23 Oct, 16:00')
    expect(formatRange('2026-10-22T13:00:00Z', '2026-10-22T17:00:00Z', JAMAICA)).toBe('Thu 22 Oct, 08:00 to 12:00')
  })

  it('uses the first station with a zone', () => {
    expect(visitZone(visit())).toBe(JAMAICA)
    expect(visitZone({ stations: [] })).toBeNull()
  })
})

describe('the schedule form', () => {
  const now = new Date('2026-10-21T12:00:00Z')
  const good = { start: '2026-10-22T08:00', end: '2026-10-22T16:00', staffIds: ['u1', 'u2'], leadId: 'u1', owners: { s1: 'u1', s2: 'u2' } }

  it('has no complaint about a good plan', () => {
    expect(validateSchedule(good, JAMAICA, now)).toEqual({})
  })

  it('asks for dates, people and stations', () => {
    const errors = validateSchedule({ start: '', end: '', staffIds: [], leadId: null, owners: {} }, JAMAICA, now)
    expect(errors.start).toBe('Choose when it starts')
    expect(errors.end).toBe('Choose when it ends')
    expect(errors.staff).toBe('Pick at least one person')
    expect(errors.stations).toBe('Pick at least one station')
  })

  it('wants the end after the start, and a visit of at most 31 days', () => {
    expect(validateSchedule({ ...good, end: '2026-10-22T07:00' }, JAMAICA, now).end).toBe('The visit must end after it starts')
    expect(validateSchedule({ ...good, end: '2026-12-22T08:00' }, JAMAICA, now).end).toBe('A visit lasts at most 31 days')
  })

  it('refuses a start well in the past, but not earlier today', () => {
    expect(validateSchedule({ ...good, start: '2026-10-10T08:00', end: '2026-10-10T16:00' }, JAMAICA, now).start).toBe('That is in the past')
    expect(validateSchedule({ ...good, start: '2026-10-21T06:00', end: '2026-10-21T16:00' }, JAMAICA, now).start).toBeUndefined()
  })

  it('wants every owner to be one of the people attending', () => {
    const errors = validateSchedule({ ...good, owners: { s1: 'u9' } }, JAMAICA, now)
    expect(errors.stations).toBe('Each station’s owner must be one of the people attending')
  })

  it('hands the lead and the stations to someone else when a person is taken off', () => {
    const next = withoutPerson(good, 'u1')
    expect(next.staffIds).toEqual(['u2'])
    expect(next.leadId).toBe('u2')
    expect(next.owners).toEqual({ s1: 'u2', s2: 'u2' })
  })

  it('leaves the lead alone when someone else is taken off', () => {
    const next = withoutPerson(good, 'u2')
    expect(next.leadId).toBe('u1')
    expect(next.owners).toEqual({ s1: 'u1', s2: 'u1' })
  })

  it('drops the stations when the last person goes', () => {
    const next = withoutPerson({ ...good, staffIds: ['u1'], owners: { s1: 'u1' } }, 'u1')
    expect(next.staffIds).toEqual([])
    expect(next.leadId).toBeNull()
    expect(next.owners).toEqual({})
  })
})

describe('the list', () => {
  it('finds a visit by reference, request, station name or code', () => {
    const v = visit()
    expect(matchesVisit(v, '')).toBe(true)
    expect(matchesVisit(v, 'vr-2026-0042')).toBe(true)
    expect(matchesVisit(v, 'rain gauge')).toBe(true)
    expect(matchesVisit(v, 'montego')).toBe(true)
    expect(matchesVisit(v, 'jm-kin')).toBe(true)
    expect(matchesVisit(v, 'radar')).toBe(false)
  })

  it('puts live visits soonest first, then the finished ones newest first', () => {
    const list = [
      visit({ id: 'old', status: 'ended', planned_start: '2026-09-01T10:00:00Z' }),
      visit({ id: 'late', planned_start: '2026-10-30T10:00:00Z' }),
      visit({ id: 'soon', planned_start: '2026-10-22T10:00:00Z' }),
      visit({ id: 'older', status: 'cancelled', planned_start: '2026-08-01T10:00:00Z' }),
    ]
    expect(sortVisits(list).map(v => v.id)).toEqual(['soon', 'late', 'old', 'older'])
  })

  it('knows which visits hold their stations', () => {
    expect(isLive('planned')).toBe(true)
    expect(isLive('started')).toBe(true)
    expect(isLive('ended')).toBe(false)
    expect(isLive('cancelled')).toBe(false)
  })

  it('names the stations, and gives an unknown status the cancelled look', () => {
    expect(stationNames(visit())).toBe('Kingston Harbour, Montego Bay Airport')
    expect(lookOfVisit('started').label).toBe('Started')
    expect(lookOfVisit('whatever').label).toBe('Cancelled')
  })

  it('asks the server which actions there are', () => {
    expect(canDo(visit({ actions: ['start'] }), 'start')).toBe(true)
    expect(canDo(visit({ actions: ['start'] }), 'end')).toBe(false)
  })

  it('says what happened at a station', () => {
    const planned = visit()
    expect(stationTimes(planned, planned.stations[0]!)).toBe('Planned for Thu 22 Oct, 08:00')
    const started = visit({ status: 'started' })
    expect(stationTimes(started, started.stations[0]!)).toBe('Not arrived')
    expect(stationTimes(started, { ...started.stations[0]!, arrived_at: '2026-10-22T13:12:00Z' })).toBe('Arrived 08:12')
    expect(stationTimes(started, { ...started.stations[0]!, arrived_at: '2026-10-22T13:12:00Z', departed_at: '2026-10-22T15:40:00Z' })).toBe('Arrived 08:12, left 10:40')
  })

  it('swaps a visit in the list, or adds it at the top', () => {
    const a = visit({ id: 'a' })
    const b = visit({ id: 'b' })
    expect(replaceVisit([a, b], { ...b, status: 'started' }).map(v => v.status)).toEqual(['planned', 'started'])
    expect(replaceVisit([a], b).map(v => v.id)).toEqual(['b', 'a'])
  })
})

describe('what the page says when the server refuses', () => {
  function problem (status: number, code: string, detail = 'x', field?: string): ApiError {
    return new ApiError(status, { status, code, detail, field })
  }

  it('says a lost connection plainly', () => {
    expect(failureOf(new NetworkError(new Error('offline')), 'fallback')).toEqual({ message: 'This needs a connection. Try again when you have signal.', reload: false })
  })

  it('knows the conflicts of a visit and reloads for the ones that mean it changed', () => {
    expect(failureOf(problem(409, 'station_in_other_visit'), 'f')).toMatchObject({ reload: false })
    expect(failureOf(problem(409, 'version_conflict'), 'f')).toMatchObject({ reload: true })
    expect(failureOf(problem(409, 'visit_cancelled'), 'f').message).toContain('cancelled')
    expect(failureOf(problem(409, 'not_owner'), 'f')).toMatchObject({ reload: true })
  })

  it('shows the server\'s own sentence for a refusal it names, with the field', () => {
    expect(failureOf(problem(422, 'bad_window', 'The visit must end after it starts', 'planned_end'), 'f'))
      .toEqual({ message: 'The visit must end after it starts', reload: false, field: 'planned_end' })
  })

  it('treats a missing visit as one to reload, and a server fault with the fallback', () => {
    expect(failureOf(problem(404, 'not_found'), 'f').reload).toBe(true)
    expect(failureOf(problem(500, 'boom'), 'fallback').message).toBe('fallback')
  })
})
