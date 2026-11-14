import type { CheckOut } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { activeCount, EMPTY_FILTERS, exportName, filtersFrom, lookOfCheck, queryFrom, resourceLabel, roleLabel, shortId, showValue, toApi } from '../audit'

// The audit log (PRD AUD-4, AUD-5; decisions W19-1, W19-4)

function check (over: Partial<CheckOut>): CheckOut {
  return {
    id: 'c-1', kind: 'manual', status: 'passed', checked: 128_402, total: 128_402, first_break_seq: null,
    requested_at: '2026-10-28T09:00:00Z', started_at: '2026-10-28T09:00:05Z', finished_at: '2026-10-28T09:01:00Z',
    requested_by_name: 'Andrea Wright', ...over,
  }
}

describe('filters in the address', () => {
  it('reads them back, ignoring what is not a word', () => {
    expect(filtersFrom({ actor: 'dev', action: 'request.approved', rtype: 'visit', org: 'o-1', from: '2026-10-01', to: '2026-10-31' })).toEqual({
      actor: 'dev', action: 'request.approved', resourceType: 'visit', org: 'o-1', from: '2026-10-01', to: '2026-10-31',
    })
    expect(filtersFrom({ actor: ['first', 'second'] }).actor).toBe('first')
    expect(filtersFrom({})).toEqual(EMPTY_FILTERS)
  })

  it('writes only the filters that are set, and counts them', () => {
    const filters = { ...EMPTY_FILTERS, actor: ' dev ', resourceType: 'visit' }
    expect(queryFrom(filters)).toMatchObject({ actor: 'dev', rtype: 'visit', action: undefined, org: undefined })
    expect(activeCount(filters)).toBe(2)
    expect(activeCount(EMPTY_FILTERS)).toBe(0)
  })

  it('turns days into a window that includes the last day', () => {
    const api = toApi({ ...EMPTY_FILTERS, from: '2026-10-20', to: '2026-10-28' })
    expect(new Date(api.since ?? '').getTime()).toBe(new Date('2026-10-20T00:00:00').getTime())
    expect(new Date(api.until ?? '').getTime()).toBe(new Date('2026-10-29T00:00:00').getTime())
    expect(toApi(EMPTY_FILTERS)).toEqual({
      actor: undefined, action: undefined, resource_type: undefined, org_id: undefined, since: undefined, until: undefined,
    })
  })
})

describe('the integrity banner', () => {
  it('says intact, when it was checked, by whom and how many records', () => {
    const look = lookOfCheck(check({}))
    expect(look).toMatchObject({ tone: 'success', running: false, title: 'The chain is intact.' })
    expect(look.text).toContain('Andrea Wright')
    expect(look.text).toContain('128,402 records')
  })

  it('credits the nightly check when no person asked', () => {
    expect(lookOfCheck(check({ requested_by_name: null, kind: 'nightly' })).text).toContain('the nightly check')
  })

  it('names the first broken record and tells the person what to do, and shows nothing else of it', () => {
    const look = lookOfCheck(check({ status: 'broken', first_break_seq: 88_411 }))
    expect(look).toMatchObject({ tone: 'error', title: 'The chain breaks at record 88,411.' })
    expect(look.text).toContain('tell whoever runs the servers')
  })

  it('shows progress while it runs, and a failed check as a warning', () => {
    const running = lookOfCheck(check({ status: 'running', checked: 84_000, finished_at: null }))
    expect(running).toMatchObject({ tone: 'info', running: true, title: 'Checking the chain.', text: '84,000 of 128,402 records.' })
    expect(lookOfCheck(check({ status: 'queued', total: null, checked: 0 })).running).toBe(true)
    expect(lookOfCheck(check({ status: 'failed' }))).toMatchObject({ tone: 'warning', running: false })
  })
})

describe('words for a record', () => {
  it('shortens a long id and leaves a short one', () => {
    expect(shortId('0192f4a8-5b1e-7c31-9a04-3e8d2f5b6c31')).toBe('0192f4a8…6c31')
    expect(shortId('audit')).toBe('audit')
  })

  it('names the resource and the role', () => {
    expect(resourceLabel('sensor_unit')).toBe('Sensor unit')
    expect(resourceLabel(undefined)).toBe('—')
    expect(roleLabel(['technician', 'admin'])).toBe('Admin')
    expect(roleLabel([])).toBe('System')
  })

  it('shows a value as text, nothing for empty and JSON for the rest', () => {
    expect(showValue('approved')).toBe('approved')
    expect(showValue(null)).toBe('nothing')
    expect(showValue('')).toBe('nothing')
    expect(showValue({ a: 1 })).toBe('{"a":1}')
    expect(showValue(0)).toBe('0')
  })

  it('names the export file from the server, or from the day', () => {
    expect(exportName('audit-log-20261028.csv')).toBe('audit-log-20261028.csv')
    expect(exportName(null, new Date('2026-10-28T12:00:00Z'))).toBe('audit-log-20261028.csv')
  })
})
