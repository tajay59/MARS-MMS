import type { NotificationOut } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { asEntityUpdate, badgeText, dayGroup, groupByDay, iconFor, isNotification, mergeNewest } from '../notifications'

function note (id: string, at: string, patch: Partial<NotificationOut> = {}): NotificationOut {
  return {
    id, type: 'request.assigned', title: 'Assigned to you', body: 'MR-2026-0034 · Logger', link: '/requests/r1',
    entity: { type: 'request', id: 'r1' }, read: false, created_at: at, ...patch,
  }
}

describe('grouping by day', () => {
  const now = new Date(2026, 9, 21, 15, 0)
  it('uses the reader’s own calendar', () => {
    expect(dayGroup(new Date(2026, 9, 21, 0, 5).toISOString(), now)).toBe('Today')
    expect(dayGroup(new Date(2026, 9, 20, 23, 55).toISOString(), now)).toBe('Yesterday')
    expect(dayGroup(new Date(2026, 9, 19, 12, 0).toISOString(), now)).toBe('Earlier')
    expect(dayGroup(new Date(2026, 9, 22, 1, 0).toISOString(), now)).toBe('Today') // a skewed clock
  })

  it('keeps the order, drops empty groups', () => {
    const items = [
      note('3', new Date(2026, 9, 21, 9, 0).toISOString()),
      note('2', new Date(2026, 9, 20, 9, 0).toISOString()),
      note('1', new Date(2026, 9, 1, 9, 0).toISOString()),
    ]
    expect(groupByDay(items, now).map(g => [g.label, g.items.map(i => i.id)])).toEqual([
      ['Today', ['3']], ['Yesterday', ['2']], ['Earlier', ['1']],
    ])
    expect(groupByDay([items[2]!], now).map(g => g.label)).toEqual(['Earlier'])
    expect(groupByDay([], now)).toEqual([])
  })
})

describe('the unread badge', () => {
  it('shows nothing for none, the number, and a cap', () => {
    expect(badgeText(0)).toBeNull()
    expect(badgeText(-1)).toBeNull()
    expect(badgeText(3)).toBe('3')
    expect(badgeText(99)).toBe('99')
    expect(badgeText(100)).toBe('99+')
  })
})

describe('merging the live list with a catch-up', () => {
  it('keeps each notification once, newest first', () => {
    const a = note('01900000-0000-7000-8000-000000000001', '2026-10-21T09:00:00Z')
    const b = note('01900000-0000-7000-8000-000000000002', '2026-10-21T09:05:00Z')
    const c = note('01900000-0000-7000-8000-000000000003', '2026-10-21T09:10:00Z')
    expect(mergeNewest([b, a], [c, b]).map(n => n.id)).toEqual([c.id, b.id, a.id])
    expect(mergeNewest([], [])).toEqual([])
  })

  it('takes the incoming copy when both have one, since it is the newer word', () => {
    const mine = note('01900000-0000-7000-8000-000000000001', '2026-10-21T09:00:00Z', { read: true })
    const late = note('01900000-0000-7000-8000-000000000001', '2026-10-21T09:00:00Z', { read: false })
    expect(mergeNewest([mine], [late])[0]!.read).toBe(false)
  })
})

describe('the messages the socket carries', () => {
  it('recognises a notification only when it has what a row needs', () => {
    expect(isNotification({ type: 'notification', data: note('n1', '2026-10-21T09:00:00Z') })).toBe(true)
    expect(isNotification({ type: 'notification', data: { id: 'n1' } })).toBe(false)
    expect(isNotification({ type: 'notification' })).toBe(false)
    expect(isNotification({ type: 'ping' })).toBe(false)
  })

  it('reads a request change and nothing else', () => {
    expect(asEntityUpdate({ type: 'entity.updated', entity: 'request', id: 'r1', status: 'assigned', kind: 'staff' }))
      .toEqual({ entity: 'request', id: 'r1', status: 'assigned', kind: 'staff' })
    expect(asEntityUpdate({ type: 'entity.updated', entity: 'station', id: 'r1', kind: 'status' })).toBeNull()
    expect(asEntityUpdate({ type: 'entity.updated', entity: 'request', id: 'r1', kind: 'other' })).toBeNull()
    expect(asEntityUpdate({ type: 'entity.updated', entity: 'request', kind: 'status' })).toBeNull()
    expect(asEntityUpdate({ type: 'notification' })).toBeNull()
  })

  it('reads a visit change with the request it belongs to', () => {
    expect(asEntityUpdate({ type: 'entity.updated', entity: 'visit', id: 'v1', request_id: 'r1', status: 'started', kind: 'visit' }))
      .toEqual({ entity: 'visit', id: 'v1', request_id: 'r1', status: 'started' })
    // Without the request a page could not tell whether it is about this one
    expect(asEntityUpdate({ type: 'entity.updated', entity: 'visit', id: 'v1', status: 'started', kind: 'visit' })).toBeNull()
    expect(asEntityUpdate({ type: 'entity.updated', entity: 'visit', request_id: 'r1', kind: 'visit' })).toBeNull()
  })

  it('has an icon for every type it names, and a bell for the rest', () => {
    for (const type of ['account.registered', 'request.submitted', 'request.assigned', 'request.staff_changed', 'request.released', 'request.cancelled', 'comment.added', 'visit.scheduled', 'visit.cancelled', 'visit.ended', 'visit.owner_changed', 'report.drafted', 'report.finalized', 'report.reopened', 'report.finalize_failed', 'report.finalize_reminder']) {
      expect(iconFor(type)).not.toBe(iconFor('something.else'))
    }
  })
})
