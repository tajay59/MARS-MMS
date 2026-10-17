import { describe, expect, it } from 'vitest'
import { formatDateTime } from '../format'

// DBD: `16 Oct 2026, 14:05 AST`, 24-hour clock, zone label; stored in UTC (rule 8).
describe('formatDateTime', () => {
  it('writes the DBD date format in the given zone', () => {
    expect(formatDateTime('2026-10-16T13:12:00Z', 'UTC')).toBe('16 Oct 2026, 13:12 UTC')
    expect(formatDateTime('2026-10-16T14:12:00Z', 'America/Jamaica')).toBe('16 Oct 2026, 09:12 EST')
    expect(formatDateTime('2026-10-16T18:05:00Z', 'America/Port_of_Spain')).toBe('16 Oct 2026, 14:05 AST')
  })

  it('uses a 24-hour clock', () => {
    expect(formatDateTime('2026-10-16T23:05:00Z', 'UTC')).toBe('16 Oct 2026, 23:05 UTC')
  })

  it('shows a dash for a missing date', () => {
    expect(formatDateTime(null)).toBe('—')
    expect(formatDateTime('not a date')).toBe('—')
  })
})
