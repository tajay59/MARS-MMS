/*
  Dates as DBD writes them: `16 Oct 2026, 14:05 AST`, a 24-hour clock with the zone label
  (TRD §13.2). Times are stored in UTC (rule 8); `timeZone` is the user’s or the station’s.
*/

/** DBD's three-letter months: newer ICU (Chrome 120+, Node 22) writes `Sept` in en-GB. */
function dbdMonths (text: string): string {
  return text.replace(/\bSept\b/, 'Sep')
}

export function formatDateTime (iso: string | null | undefined, timeZone?: string | null): string {
  if (!iso) {
    return '—'
  }
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return '—'
  }
  const zone = timeZone ?? undefined
  const parts = new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZone: zone,
  }).formatToParts(date)
  // en-US names the Americas' zones (AST, EST); en-GB would write GMT-4.
  const label = new Intl.DateTimeFormat('en-US', { timeZone: zone, timeZoneName: 'short' })
    .formatToParts(date)
    .find(p => p.type === 'timeZoneName')
    ?.value ?? ''
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find(p => p.type === type)?.value ?? ''
  return dbdMonths(`${part('day')} ${part('month')} ${part('year')}, ${part('hour')}:${part('minute')} ${label}`.trim())
}

/**
  A list's short time, as a message list writes it: `14:09` today, `Fri` within the last six
  days, `4 Oct` this year, `4 Oct 2025` before. Days are counted in `timeZone`. The full date
  goes in the row's `title` and `datetime`.
*/
export function formatListTime (iso: string | null | undefined, timeZone?: string | null, now: Date = new Date()): string {
  if (!iso) {
    return '—'
  }
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return '—'
  }
  const zone = timeZone ?? undefined
  const day = (d: Date): { y: number, m: number, d: number } => {
    const parts = new Intl.DateTimeFormat('en-GB', { year: 'numeric', month: 'numeric', day: 'numeric', timeZone: zone }).formatToParts(d)
    const part = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find(p => p.type === type)?.value)
    return { y: part('year'), m: part('month'), d: part('day') }
  }
  const then = day(date)
  const today = day(now)
  const daysAgo = Math.round((Date.UTC(today.y, today.m - 1, today.d) - Date.UTC(then.y, then.m - 1, then.d)) / 86_400_000)
  const format = (options: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('en-GB', { ...options, timeZone: zone }).format(date)
  if (daysAgo <= 0) {
    return format({ hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
  }
  if (daysAgo < 7) {
    return format({ weekday: 'short' })
  }
  return dbdMonths(format(then.y === today.y ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: 'numeric' }))
}

function validDate (iso: string | null | undefined): Date | null {
  if (!iso) {
    return null
  }
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date
}

/** A day in a table: `10 Jan 2026`, in `timeZone` (the station's for station records). */
export function formatDate (iso: string | null | undefined, timeZone?: string | null): string {
  const date = validDate(iso)
  if (!date) {
    return '—'
  }
  return dbdMonths(new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: timeZone ?? undefined }).format(date))
}

/** A day in running text or a chip: `14 Feb` this year, `14 Feb 2025` in another. */
export function formatShortDate (iso: string | null | undefined, timeZone?: string | null, now: Date = new Date()): string {
  const date = validDate(iso)
  if (!date) {
    return '—'
  }
  const zone = timeZone ?? undefined
  const year = (d: Date) => new Intl.DateTimeFormat('en-GB', { year: 'numeric', timeZone: zone }).format(d)
  const options: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', timeZone: zone }
  if (year(date) !== year(now)) {
    options.year = 'numeric'
  }
  return dbdMonths(new Intl.DateTimeFormat('en-GB', options).format(date))
}

/** A calendar date with no time or zone (`2019-03-14`, an install date) as `14 Mar 2019`. */
export function formatPlainDate (value: string | null | undefined): string {
  const match = value ? /^(\d{4})-(\d{2})-(\d{2})/.exec(value) : null
  if (!match) {
    return '—'
  }
  const [, y, m, d] = match.map(Number) as [number, number, number, number]
  return dbdMonths(new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
    .format(new Date(Date.UTC(y, m - 1, d))))
}

/** The short name of an IANA zone at `at` (`EST`, `AST`); the IANA name when there is none. */
export function zoneAbbreviation (timeZone: string, at: Date = new Date()): string {
  try {
    return new Intl.DateTimeFormat('en-US', { timeZone, timeZoneName: 'short' })
      .formatToParts(at)
      .find(p => p.type === 'timeZoneName')
      ?.value ?? timeZone
  } catch {
    return timeZone
  }
}

/** `17.9714° N, 76.7920° W`: four decimals is about 11 m, enough to find a mast. */
export function formatCoordinates (latitude: number, longitude: number): string {
  const part = (value: number, positive: string, negative: string) =>
    `${Math.abs(value).toFixed(4)}° ${value < 0 ? negative : positive}`
  return `${part(latitude, 'N', 'S')}, ${part(longitude, 'E', 'W')}`
}
