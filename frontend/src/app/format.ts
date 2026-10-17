/*
  Dates as DBD writes them: `16 Oct 2026, 14:05 AST`, a 24-hour clock with the zone label
  (TRD §13.2). Times are stored in UTC (rule 8); `timeZone` is the user’s or the station’s.
*/

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
  return `${part('day')} ${part('month')} ${part('year')}, ${part('hour')}:${part('minute')} ${label}`.trim()
}
