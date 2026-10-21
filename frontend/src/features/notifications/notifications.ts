import type { NotificationOut } from '@/api/models'
import type { EntityUpdate, VisitUpdate } from '@/app/realtime/bus'
import { mdiAccountCheckOutline, mdiAccountOutline, mdiBellOutline, mdiCalendarOutline, mdiCancel, mdiCommentTextOutline, mdiFlagCheckered, mdiInboxOutline, mdiReplay, mdiSwapHorizontal, mdiTuneVariant } from '@mdi/js'

/*
  The notification list and the messages the socket carries (PRD NOT-1, NOT-2, NOT-5). No Vue
  here, so Vitest covers it directly.
*/

export type DayGroup = 'Today' | 'Yesterday' | 'Earlier'

function startOfDay (date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}

/** Today, Yesterday or Earlier, by the reader's own calendar. */
export function dayGroup (createdAt: string, now: Date = new Date()): DayGroup {
  const days = Math.round((startOfDay(now) - startOfDay(new Date(createdAt))) / 86_400_000)
  if (days <= 0) {
    return 'Today'
  }
  return days === 1 ? 'Yesterday' : 'Earlier'
}

export interface Group {
  label: DayGroup
  items: NotificationOut[]
}

/** The list newest first, split by day, empty groups left out. */
export function groupByDay (items: readonly NotificationOut[], now: Date = new Date()): Group[] {
  const groups = new Map<DayGroup, NotificationOut[]>()
  for (const item of items) {
    const label = dayGroup(item.created_at, now)
    groups.set(label, [...groups.get(label) ?? [], item])
  }
  return (['Today', 'Yesterday', 'Earlier'] as const)
    .filter(label => groups.has(label))
    .map(label => ({ label, items: groups.get(label) ?? [] }))
}

/** The icon of a notification's type; one meaning, one icon (DBD Iconography). */
export function iconFor (type: string): string {
  switch (type) {
    case 'account.registered': {
      return mdiAccountCheckOutline
    }
    case 'request.submitted': {
      return mdiInboxOutline
    }
    case 'request.assigned':
    case 'request.staff_changed': {
      return mdiAccountOutline
    }
    case 'request.released': {
      return mdiReplay
    }
    case 'request.cancelled': {
      return mdiCancel
    }
    case 'comment.added': {
      return mdiCommentTextOutline
    }
    case 'calibration.digest': {
      return mdiTuneVariant
    }
    case 'visit.scheduled': {
      return mdiCalendarOutline
    }
    case 'visit.cancelled': {
      return mdiCancel
    }
    case 'visit.ended': {
      return mdiFlagCheckered
    }
    case 'visit.owner_changed': {
      return mdiSwapHorizontal
    }
    default: {
      return mdiBellOutline
    }
  }
}

/** `12`, `99+`: what the badge shows. Nothing for none. */
export function badgeText (unread: number): string | null {
  if (unread <= 0) {
    return null
  }
  return unread > 99 ? '99+' : String(unread)
}

export function isNotification (message: Record<string, unknown>): message is { type: 'notification', data: NotificationOut } {
  const data = message.data as Partial<NotificationOut> | undefined
  return message.type === 'notification' && typeof data?.id === 'string' && typeof data.title === 'string'
}

/** The "a request or a visit changed" message, or null for anything else (or anything malformed). */
export function asEntityUpdate (message: Record<string, unknown>): EntityUpdate | VisitUpdate | null {
  if (message.type === 'entity.updated' && message.entity === 'visit') {
    return typeof message.id === 'string' && typeof message.request_id === 'string'
      ? { entity: 'visit', id: message.id, request_id: message.request_id, status: String(message.status ?? '') }
      : null
  }
  if (message.type !== 'entity.updated' || message.entity !== 'request' || typeof message.id !== 'string') {
    return null
  }
  const kind = String(message.kind)
  if (!['status', 'staff', 'comment'].includes(kind)) {
    return null
  }
  return { entity: 'request', id: message.id, status: String(message.status ?? ''), kind: kind as EntityUpdate['kind'] }
}

/** Newest first, each once: a live message and the catch-up can carry the same notification. */
export function mergeNewest (existing: readonly NotificationOut[], incoming: readonly NotificationOut[]): NotificationOut[] {
  const byId = new Map<string, NotificationOut>()
  for (const item of [...incoming, ...existing]) {
    if (!byId.has(item.id)) {
      byId.set(item.id, item)
    }
  }
  // Fresh array: sorting it in place is safe, and toSorted needs iOS 16. UUIDv7 IDs sort by time.
  // eslint-disable-next-line unicorn/no-array-sort
  return [...byId.values()].sort((a, b) => b.id.localeCompare(a.id))
}
