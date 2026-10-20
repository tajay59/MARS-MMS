import type { RequestDetail, RequestHistoryEntry, RequestSummary } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/problem'
import {
  createBody,
  emptyValues,
  isUnchanged,
  patchBody,
  problemOf,
  validate,
  valuesOf,
} from '../requestFormModel'
import {
  bannerFor,
  createdSince,
  extraFilterCount,
  facetsOf,
  filtersFrom,
  lookOf,
  matches,
  matchesOthers,
  queryFrom,
  showsInList,
  STAGES,
  stationsLabel,
  STATUSES,
  statusLook,
  timelineOf,
} from '../requests'

function summary (patch: Partial<RequestSummary> = {}): RequestSummary {
  return {
    id: 'r1', ref: 'MR-2026-0042', title: 'Rain gauge not reporting', category: 'fault', priority: 'high',
    status: 'submitted', org_id: 'o1', org_name: 'Organization A',
    stations: [{ id: 's1', code: 'JM-KIN-001', name: 'Kingston Harbour', country: 'JM' }],
    requested_by: { id: 'u1', name: 'Maria Clarke' }, assigned_staff: [],
    created_at: '2026-10-14T09:12:00Z', updated_at: '2026-10-14T09:12:00Z', ...patch,
  }
}

function detail (patch: Partial<RequestDetail> = {}): RequestDetail {
  return {
    ...summary(), description: 'The gauge stopped on Saturday.', denial_reason: null, cancel_reason: null,
    status_history: [{ from_status: null, to_status: 'submitted', at: '2026-10-14T09:12:00Z', by: { id: 'u1', name: 'Maria Clarke' }, note: null }],
    milestones: { submitted_at: '2026-10-14T09:12:00Z' }, version: 1, actions: ['cancel', 'edit'], ...patch,
  } as RequestDetail
}

function entry (to: string, at: string, by = 'Andrea Walker', note: string | null = null): RequestHistoryEntry {
  return { from_status: null, to_status: to, at, by: { id: 'a', name: by }, note }
}

describe('statuses', () => {
  it('has a look for every status, with an icon, a word and a colour pair', () => {
    for (const status of STATUSES) {
      const look = statusLook[status]
      expect(look.label).toBeTruthy()
      expect(look.icon).toMatch(/^M/)
      expect(look.chip).toMatch(/text-on-status-/)
    }
    expect(new Set(STATUSES.map(s => statusLook[s].label)).size).toBe(STATUSES.length)
  })

  it('shows an unknown status as cancelled instead of failing', () => {
    expect(lookOf('nonsense')).toBe(statusLook.cancelled)
  })

  it('shows High and Urgent in the list and leaves Low and Normal to the page', () => {
    expect(['low', 'normal', 'high', 'urgent'].map(p => showsInList(p))).toEqual([false, false, true, true])
  })

  it('names a request’s stations in one line', () => {
    expect(stationsLabel(summary())).toBe('JM-KIN-001')
    expect(stationsLabel(summary({ stations: [...summary().stations, { id: 's2', code: 'JM-MBJ-002', name: 'x', country: 'JM' }] }))).toBe('JM-KIN-001 +1')
    expect(stationsLabel(summary({ stations: [] }))).toBe('—')
  })
})

describe('filters in the URL', () => {
  it('reads what is valid and ignores the rest', () => {
    const f = filtersFrom({ q: ' gauge ', status: 'approved', category: 'power', priority: 'urgent', created: '30', org: 'o1', country: 'JM' })
    expect(f).toEqual({ q: 'gauge', status: 'approved', org: 'o1', country: 'JM', category: 'power', priority: 'urgent', created: '30' })
    const bad = filtersFrom({ status: 'nope', category: 'weather', priority: 'now', created: 'forever' })
    expect(bad).toEqual({ q: '', status: null, org: null, country: null, category: null, priority: null, created: 'any' })
  })

  it('writes only the filters that are set', () => {
    expect(queryFrom(filtersFrom({}))).toEqual({
      q: undefined, status: undefined, org: undefined, country: undefined, category: undefined, priority: undefined, created: undefined,
    })
    expect(queryFrom(filtersFrom({ status: 'approved', created: '7' }))).toMatchObject({ status: 'approved', created: '7' })
  })

  it('counts the filters the status options do not cover', () => {
    expect(extraFilterCount(filtersFrom({}))).toBe(0)
    expect(extraFilterCount(filtersFrom({ status: 'approved', org: 'o1', created: '7' }))).toBe(2)
  })

  it('filters by text, status, organization, country, category, priority and date', () => {
    const now = new Date('2026-10-20T12:00:00Z')
    const r = summary()
    expect(matches(r, filtersFrom({ q: 'MR-2026-0042' }), now)).toBe(true)
    expect(matches(r, filtersFrom({ q: 'jm-kin' }), now)).toBe(true) // a station code
    expect(matches(r, filtersFrom({ q: 'modem' }), now)).toBe(false)
    expect(matches(r, filtersFrom({ status: 'approved' }), now)).toBe(false)
    expect(matches(r, filtersFrom({ org: 'o2' }), now)).toBe(false)
    expect(matches(r, filtersFrom({ country: 'TT' }), now)).toBe(false)
    expect(matches(r, filtersFrom({ country: 'JM' }), now)).toBe(true)
    expect(matches(r, filtersFrom({ category: 'power' }), now)).toBe(false)
    expect(matches(r, filtersFrom({ priority: 'high' }), now)).toBe(true)
    expect(matches(r, filtersFrom({ created: '7' }), now)).toBe(true) // six days old
    expect(matches(r, filtersFrom({ created: '7' }), new Date('2026-10-25T12:00:00Z'))).toBe(false) // eleven
    expect(matches(r, filtersFrom({ created: '30' }), now)).toBe(true)
    expect(matches(r, filtersFrom({ created: 'year' }), now)).toBe(true)
  })

  it('counts a status against every filter but status', () => {
    const f = filtersFrom({ status: 'approved', category: 'fault' })
    expect(matchesOthers(summary({ status: 'closed' }), f)).toBe(true)
    expect(matchesOthers(summary({ category: 'power' }), f)).toBe(false)
  })

  it('knows where each date preset starts', () => {
    const now = new Date('2026-10-20T12:00:00Z')
    expect(createdSince('any', now)).toBeNull()
    expect(createdSince('7', now)).toBe(now.getTime() - 7 * 86_400_000)
    expect(createdSince('year', now)).toBe(Date.UTC(2026, 0, 1))
  })

  it('lists the organizations and countries the requests have', () => {
    const facets = facetsOf([
      summary(),
      summary({ id: 'r2', org_id: 'o2', org_name: 'Another Org', stations: [{ id: 's9', code: 'TT-POS-001', name: 'x', country: 'TT' }] }),
    ])
    expect(facets.orgs.map(o => o.name)).toEqual(['Another Org', 'Organization A'])
    expect(facets.countries).toEqual(['JM', 'TT'])
  })
})

describe('the status timeline', () => {
  it('shows the stages reached and the ones still to come as hollow', () => {
    const steps = timelineOf([entry('submitted', '2026-10-14T09:12:00Z'), entry('approved', '2026-10-15T08:40:00Z')], 'approved')
    expect(steps.map(s => [s.status, s.future, s.current])).toEqual([
      ['submitted', false, false], ['approved', false, true], ['assigned', true, false],
      ['scheduled', true, false], ['in_progress', true, false], ['client_review', true, false], ['closed', true, false],
    ])
    expect(steps[1]?.at).toBe('2026-10-15T08:40:00Z')
    expect(steps.at(2)?.at).toBeNull()
  })

  it('leaves out a stage that was skipped', () => {
    const steps = timelineOf([entry('submitted', 'a'), entry('approved', 'b'), entry('assigned', 'c'), entry('in_progress', 'd')], 'in_progress')
    expect(steps.map(s => s.status)).not.toContain('scheduled')
    expect(steps.filter(s => !s.future).map(s => s.status)).toEqual(['submitted', 'approved', 'assigned', 'in_progress'])
  })

  it('ends a denied or cancelled request where it stopped', () => {
    const denied = timelineOf([entry('submitted', 'a'), entry('denied', 'b')], 'denied')
    expect(denied.map(s => s.status)).toEqual(['submitted', 'denied'])
    expect(denied.every(s => !s.future)).toBe(true)
    const cancelled = timelineOf([entry('submitted', 'a'), entry('approved', 'b'), entry('cancelled', 'c')], 'cancelled')
    expect(cancelled.map(s => s.status)).toEqual(['submitted', 'approved', 'cancelled'])
    expect(cancelled.at(-1)?.current).toBe(true)
  })

  it('has the seven stages in the order of PRD 5.1', () => {
    expect(STAGES).toEqual(['submitted', 'approved', 'assigned', 'scheduled', 'in_progress', 'client_review', 'closed'])
  })
})

describe('the banner', () => {
  it('speaks to a client and to staff in their own words', () => {
    expect(bannerFor(detail(), true)?.body).toMatch(/We’ll tell you/)
    expect(bannerFor(detail(), false)?.body).toBe('Submitted by Maria Clarke, Organization A.')
  })

  it('gives a denial’s reason and who denied it', () => {
    const banner = bannerFor(detail({ status: 'denied', denial_reason: 'Out of scope', status_history: [entry('denied', 'a')] }), true)
    expect(banner).toEqual({ tone: 'error', title: 'Denied by Andrea Walker', body: 'Reason: Out of scope' })
  })

  it('has none while work is under way', () => {
    expect(bannerFor(detail({ status: 'in_progress' }), false)).toBeNull()
  })
})

describe('the form', () => {
  const ok = { ...emptyValues(['s1']), title: 'Wind sensor stuck', description: 'The cups do not turn.' }

  it('asks for the same things the server does', () => {
    expect(validate(emptyValues(), { admin: false, editing: false })).toEqual({
      stationIds: 'Pick at least one station', title: 'Add a title', description: 'Describe the problem',
    })
    expect(validate(ok, { admin: false, editing: false })).toEqual({})
    expect(validate({ ...ok, title: '  ' }, { admin: false, editing: false }).title).toBe('Add a title')
    expect(validate({ ...ok, title: 'x'.repeat(201) }, { admin: false, editing: false }).title).toMatch(/under 200/)
  })

  it('makes an admin choose the organization, but only for a new request', () => {
    expect(validate(ok, { admin: true, editing: false }).orgId).toBe('Choose the organization')
    expect(validate(ok, { admin: true, editing: true }).orgId).toBeUndefined()
    expect(validate({ ...ok, orgId: 'o1' }, { admin: true, editing: false }).orgId).toBeUndefined()
  })

  it('sends a clean body with the ID the device made', () => {
    expect(createBody({ ...ok, title: '  Wind  ' }, 'id-1', { admin: false })).toMatchObject({ id: 'id-1', title: 'Wind', org_id: null, station_ids: ['s1'] })
    expect(createBody({ ...ok, orgId: 'o1' }, 'id-2', { admin: true }).org_id).toBe('o1')
  })

  it('sends only what changed, with the version', () => {
    const d = detail()
    const same = valuesOf(d)
    expect(patchBody(same, d)).toEqual({ version: 1 })
    expect(isUnchanged(same, d)).toBe(true)
    expect(patchBody({ ...same, title: 'New', priority: 'urgent' }, d)).toEqual({ version: 1, title: 'New', priority: 'urgent' })
    expect(patchBody({ ...same, stationIds: ['s1', 's2'] }, d)).toEqual({ version: 1, station_ids: ['s1', 's2'] })
    expect(isUnchanged({ ...same, title: ' Rain gauge not reporting ' }, d)).toBe(true) // trimmed
  })

  it('turns the server’s refusals into messages on the field they are about', () => {
    const named = new ApiError(422, { code: 'unknown_station', detail: 'That station isn’t one of this organization’s', field: 'station_ids' })
    expect(problemOf(named)).toEqual({ kind: 'fields', errors: { stationIds: 'That station isn’t one of this organization’s' }, message: null })
    expect(problemOf(new ApiError(409, { code: 'version_conflict', detail: 'stale' })).kind).toBe('stale')
    expect(problemOf(new ApiError(409, { code: 'request_changed', detail: 'changed' })).kind).toBe('stale')
    const listed = new ApiError(422, { code: 'validation_failed', detail: 'bad', errors: [{ loc: ['body', 'title'], msg: 'Too long' }] })
    expect(problemOf(listed)).toEqual({ kind: 'fields', errors: { title: 'Too long' }, message: null })
    expect(problemOf(new ApiError(409, { code: 'request_locked', detail: 'Locked' }))).toEqual({ kind: 'fields', errors: {}, message: 'Locked' })
    expect(problemOf(new ApiError(500, {})).kind).toBe('other')
  })
})
