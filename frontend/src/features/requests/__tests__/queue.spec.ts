import type { QueueItem, RequestDetail } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from '@/api/problem'
import {
  assignable,
  countBy,
  filterQueue,
  openLabel,
  queueFiltersFrom,
  queueQueryFrom,
  roleLabel,
  sameStaff,
  staffOptions,
  waitingLabel,
} from '../queue'
import { bannerFor, joinNames } from '../requests'
import { failureOf, namesOf } from '../staffingActions'

function item (patch: Partial<QueueItem> = {}): QueueItem {
  return {
    id: 'r1', ref: 'MR-2026-0031', title: 'Rain gauge reads zero', category: 'fault', priority: 'high',
    status: 'approved', org_id: 'o1', org_name: 'Met Service A',
    stations: [{ id: 's1', code: 'KGN-014', name: 'Hope Valley', country: 'JM' }],
    requested_by: null, assigned_staff: [], approved_at: '2026-10-14T09:00:00Z',
    created_at: '2026-10-14T08:00:00Z', updated_at: '2026-10-14T09:00:00Z', ...patch,
  }
}

describe('the queue filters', () => {
  it('reads them from the URL and drops what is unknown', () => {
    expect(queueFiltersFrom({ q: ' wind ', country: 'JM', priority: 'urgent', category: 'power' }))
      .toEqual({ q: 'wind', country: 'JM', priority: 'urgent', category: 'power' })
    expect(queueFiltersFrom({ priority: 'now', category: 'x', q: ['a', 'b'] }))
      .toEqual({ q: 'a', country: null, priority: null, category: null })
    expect(queueQueryFrom(queueFiltersFrom({}))).toEqual({
      q: undefined, country: undefined, priority: undefined, category: undefined,
    })
  })

  it('narrows the queue by every filter together', () => {
    const rows = [
      item({ id: 'a' }),
      item({ id: 'b', priority: 'low', category: 'power', stations: [{ id: 's2', code: 'POS-021', name: 'Port', country: 'TT' }] }),
    ]
    expect(filterQueue(rows, queueFiltersFrom({})).map(r => r.id)).toEqual(['a', 'b'])
    expect(filterQueue(rows, queueFiltersFrom({ country: 'TT' })).map(r => r.id)).toEqual(['b'])
    expect(filterQueue(rows, queueFiltersFrom({ q: 'pos-0' })).map(r => r.id)).toEqual(['b'])
    expect(filterQueue(rows, queueFiltersFrom({ q: 'mr-2026-0031' })).map(r => r.id)).toEqual(['a', 'b'])
    expect(filterQueue(rows, queueFiltersFrom({ priority: 'high', category: 'power' }))).toEqual([])
  })

  it('counts each option over what the other filters leave', () => {
    const rows = [
      item({ id: 'a' }),
      item({ id: 'b', priority: 'low' }),
      item({ id: 'c', priority: 'low', stations: [{ id: 's2', code: 'POS-021', name: 'Port', country: 'TT' }] }),
    ]
    const none = queueFiltersFrom({})
    expect(countBy(rows, none, 'country')).toEqual(new Map([['JM', 2], ['TT', 1]]))
    expect(countBy(rows, none, 'priority')).toEqual(new Map([['high', 1], ['low', 2]]))
    // Choosing Jamaica changes the priority counts, but not the country counts (so you can switch)
    const jm = queueFiltersFrom({ country: 'JM' })
    expect(countBy(rows, jm, 'priority')).toEqual(new Map([['high', 1], ['low', 1]]))
    expect(countBy(rows, jm, 'country')).toEqual(new Map([['JM', 2], ['TT', 1]]))
  })
})

describe('how long a request has waited', () => {
  const now = new Date('2026-10-20T12:00:00Z')
  it.each([
    ['2026-10-20T11:59:50Z', '1 minute'],
    ['2026-10-20T11:15:00Z', '45 minutes'],
    ['2026-10-20T07:00:00Z', '5 hours'],
    ['2026-10-20T11:00:00Z', '1 hour'],
    ['2026-10-19T11:00:00Z', '1 day'],
    ['2026-10-14T12:00:00Z', '6 days'],
  ])('%s is %s', (since, label) => {
    expect(waitingLabel(since, now)).toBe(label)
  })

  it('has nothing to say without a time', () => {
    expect(waitingLabel(null, now)).toBe('—')
  })
})

describe('choosing staff', () => {
  const users = [
    { id: 'b', name: 'Maya Clarke', roles: ['technician'], status: 'active' },
    { id: 'a', name: 'Andrea Ortiz', roles: ['admin'], status: 'active' },
    { id: 'a', name: 'Andrea Ortiz', roles: ['admin', 'technician'], status: 'active' },
    { id: 'c', name: 'Old Hand', roles: ['technician'], status: 'disabled' },
    { id: 'd', name: 'Just Viewing', roles: ['viewer'], status: 'active' },
  ]

  it('lists active technicians and admins once, by name', () => {
    expect(assignable(users).map(p => p.name)).toEqual(['Andrea Ortiz', 'Maya Clarke'])
  })

  it('shows open requests and what is chosen, and searches by name', () => {
    const people = assignable(users)
    const options = staffOptions(people, { b: 3 }, new Set(['b']), '')
    expect(options.map(o => [o.id, o.open, o.chosen])).toEqual([['a', 0, false], ['b', 3, true]])
    expect(staffOptions(people, {}, new Set(), ' MAYA ').map(o => o.id)).toEqual(['b'])
  })

  it('words things the way the screen does', () => {
    expect(openLabel(1)).toBe('1 open request')
    expect(openLabel(0)).toBe('0 open requests')
    expect(roleLabel(['technician', 'admin'])).toBe('Admin')
    expect(roleLabel(['technician'])).toBe('Technician')
    expect(sameStaff(['a', 'b'], ['b', 'a'])).toBe(true)
    expect(sameStaff(['a'], ['a', 'b'])).toBe(false)
  })

  it('joins names', () => {
    expect(joinNames([])).toBe('')
    expect(joinNames(['A'])).toBe('A')
    expect(joinNames(['A', 'B'])).toBe('A and B')
    expect(joinNames(['A', 'B', 'C'])).toBe('A, B and C')
  })
})

describe('what a failed claim says', () => {
  it('names who got there first and reloads', () => {
    const lost = new ApiError(409, { code: 'already_assigned', detail: 'x', claimed_by: ['Devon Brown'] })
    expect(failureOf(lost, 'claim')).toEqual({ ok: false, message: 'Devon Brown claimed it first.', reload: true })
    expect(namesOf(['A', 3, 'B'])).toEqual(['A', 'B'])
    expect(namesOf(null)).toEqual([])
  })

  it('does not blame the person for the network, and reloads for a changed request', () => {
    expect(failureOf(new NetworkError(new Error('x')), 'claim')).toMatchObject({ reload: false })
    expect(failureOf(new ApiError(409, { code: 'request_changed' }), 'release')).toMatchObject({ reload: true })
    expect(failureOf(new ApiError(404, {}), 'claim')).toMatchObject({ reload: true })
    expect(failureOf(new ApiError(500, {}), 'release').message).toBe('We couldn’t release it. Try again in a moment.')
  })
})

describe('the request page banner for staffing', () => {
  const base = { status_history: [], assigned_staff: [], org_name: 'Org', requested_by: null } as unknown as RequestDetail

  it('tells staff the request is in the queue, and a client only that it is approved', () => {
    const approved = { ...base, status: 'approved' } as RequestDetail
    expect(bannerFor(approved, false)?.title).toBe('In the queue')
    expect(bannerFor(approved, true)?.title).toBe('Approved')
  })

  it('names the people on an assigned request', () => {
    const assigned = {
      ...base, status: 'assigned', assigned_staff: [{ id: '1', name: 'Devon Brown' }, { id: '2', name: 'Maya Clarke' }],
    } as RequestDetail
    expect(bannerFor(assigned, true)).toMatchObject({ title: 'A technician is on it', body: 'Assigned to Devon Brown and Maya Clarke.' })
    expect(bannerFor(assigned, false)?.body).toBe('On it: Devon Brown and Maya Clarke.')
  })
})
