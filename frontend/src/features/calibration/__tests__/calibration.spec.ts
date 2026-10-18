import type { DueUnit } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { countDue, dueFiltersFrom, dueQueryFrom, dueText, matchesDue, sortDue } from '../calibration'

const NOW = new Date('2026-10-18T12:00:00Z')
const day = (n: number) => new Date(NOW.getTime() + n * 86_400_000).toISOString()

function unit (id: string, dueInDays: number, station: Partial<NonNullable<DueUnit['station']>> | null = {}): DueUnit {
  return {
    unit_id: id,
    serial: id,
    status: 'installed',
    parameter: 'AT',
    last_calibrated_at: null,
    calibration_due_at: day(dueInDays),
    due_state: dueInDays < 0 ? 'overdue' : 'due_soon',
    model: { id: 'm1', kind: 'sensor', manufacturer: 'Vaisala', model: 'HMP155' },
    station: station === null ? null : { id: 's1', code: 'JM-KIN-001', name: 'Kingston Harbour', country: 'JM', owner_org_id: 'org-a', owner_org_name: 'Organization A', ...station },
  }
}

describe('filters', () => {
  it('defaults to 30 days and accepts only the windows on offer', () => {
    expect(dueFiltersFrom({}).within).toBe(30)
    expect(dueFiltersFrom({ within: '90' }).within).toBe(90)
    expect(dueFiltersFrom({ within: '45' }).within).toBe(30)
    expect(dueFiltersFrom({ within: 'x', org: 'o1', country: 'JM' })).toEqual({ within: 30, org: 'o1', country: 'JM' })
  })

  it('keeps the default window out of the URL', () => {
    expect(dueQueryFrom({ within: 30, org: null, country: null })).toEqual({ within: undefined, org: undefined, country: undefined })
    expect(dueQueryFrom({ within: 60, org: 'o1', country: null }).within).toBe('60')
  })

  it('narrows by organization and country', () => {
    const u = unit('a', 5, { owner_org_id: 'org-b', country: 'TT' })
    expect(matchesDue(u, { within: 30, org: null, country: null })).toBe(true)
    expect(matchesDue(u, { within: 30, org: 'org-b', country: 'TT' })).toBe(true)
    expect(matchesDue(u, { within: 30, org: 'org-a', country: null })).toBe(false)
    expect(matchesDue(u, { within: 30, org: null, country: 'JM' })).toBe(false)
    expect(matchesDue(unit('b', 5, null), { within: 30, org: 'org-a', country: null })).toBe(false)
  })
})

describe('wording and order', () => {
  it('says how far overdue or ahead', () => {
    expect(dueText(day(-45), NOW)).toBe('Overdue 45 days')
    expect(dueText(day(-1.5), NOW)).toBe('Overdue 1 day')
    expect(dueText(new Date(NOW.getTime() - 3_600_000).toISOString(), NOW)).toBe('Overdue today')
    expect(dueText(day(21), NOW)).toBe('Due in 21 days')
    expect(dueText(day(0.5), NOW)).toBe('Due tomorrow')
  })

  it('puts the longest overdue first', () => {
    const sorted = sortDue([unit('soon', 21), unit('late', -45), unit('later', -2)])
    expect(sorted.map(u => u.unit_id)).toEqual(['late', 'later', 'soon'])
  })

  it('counts overdue and due soon', () => {
    expect(countDue([unit('a', -1), unit('b', 3), unit('c', 20)], NOW)).toEqual({ overdue: 1, soon: 2 })
  })
})
