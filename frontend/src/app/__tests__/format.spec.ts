import { describe, expect, it } from 'vitest'
import {
  formatCoordinates,
  formatDate,
  formatDateTime,
  formatListTime,
  formatPlainDate,
  formatShortDate,
  zoneAbbreviation,
} from '../format'

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

describe('formatListTime', () => {
  // Saturday 17 Oct 2026, 15:00 in Jamaica (UTC-5)
  const now = new Date('2026-10-17T20:00:00Z')
  const zone = 'America/Jamaica'

  it('writes the time for today, counted in the zone', () => {
    expect(formatListTime('2026-10-17T14:09:00Z', zone, now)).toBe('09:09')
    // 00:30 UTC on the 18th is still the 17th in Jamaica
    expect(formatListTime('2026-10-18T00:30:00Z', zone, now)).toBe('19:30')
  })

  it('writes the weekday within the last six days', () => {
    expect(formatListTime('2026-10-16T15:00:00Z', zone, now)).toBe('Fri')
    expect(formatListTime('2026-10-11T15:00:00Z', zone, now)).toBe('Sun')
  })

  it('writes the day and month this year, and the year before that', () => {
    expect(formatListTime('2026-10-10T15:00:00Z', zone, now)).toBe('10 Oct')
    expect(formatListTime('2025-12-24T15:00:00Z', zone, now)).toBe('24 Dec 2025')
  })

  it('shows a dash for a missing date', () => {
    expect(formatListTime(undefined, zone, now)).toBe('—')
  })
})

describe('station dates and places', () => {
  const now = new Date('2026-10-18T12:00:00Z')

  it('writes a day in the station’s zone', () => {
    expect(formatDate('2026-01-10T03:00:00Z', 'America/Jamaica')).toBe('9 Jan 2026')
    expect(formatDate(null)).toBe('—')
  })

  it('leaves out this year in a short date', () => {
    expect(formatShortDate('2026-02-14T12:00:00Z', 'UTC', now)).toBe('14 Feb')
    expect(formatShortDate('2025-02-14T12:00:00Z', 'UTC', now)).toBe('14 Feb 2025')
  })

  it('writes September as Sep, as DBD does, whatever the browser’s ICU', () => {
    expect(formatDate('2024-09-15T12:00:00Z', 'UTC')).toBe('15 Sep 2024')
    expect(formatShortDate('2026-09-15T12:00:00Z', 'UTC', now)).toBe('15 Sep')
    expect(formatPlainDate('2026-09-01')).toBe('1 Sep 2026')
    expect(formatDateTime('2026-09-16T13:12:00Z', 'UTC')).toBe('16 Sep 2026, 13:12 UTC')
  })

  it('reads a calendar date without shifting it by a zone', () => {
    expect(formatPlainDate('2019-03-14')).toBe('14 Mar 2019')
    expect(formatPlainDate('14/03/2019')).toBe('—')
  })

  it('names the zone, or falls back to its IANA name', () => {
    expect(zoneAbbreviation('America/Jamaica', now)).toBe('EST')
    expect(zoneAbbreviation('Not/A_Zone', now)).toBe('Not/A_Zone')
  })

  it('writes coordinates with hemispheres to four decimals', () => {
    expect(formatCoordinates(17.97141, -76.792)).toBe('17.9714° N, 76.7920° W')
    expect(formatCoordinates(-1.5, 36.8)).toBe('1.5000° S, 36.8000° E')
  })
})
