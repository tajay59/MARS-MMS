import { describe, expect, it } from 'vitest'
import { STATUSES } from '@/features/requests/requests'
import { currentSection, REVIEW_CLOCK, SECTIONS, STATUS_ROWS } from '../clientGuide'

describe('client guide (W23-5)', () => {
  it('explains every request status, in the app’s order', () => {
    expect(STATUS_ROWS.map(r => r.status)).toEqual([...STATUSES])
  })

  it('has one anchor per section, each unique', () => {
    expect(new Set(SECTIONS.map(s => s.id)).size).toBe(SECTIONS.length)
    expect(SECTIONS.every(s => /^[a-z-]+$/.test(s.id))).toBe(true)
  })

  it('ends the review clock on day 30, after the reminders', () => {
    expect(REVIEW_CLOCK.map(s => s.day)).toEqual([0, 7, 21, 28, 30])
  })

  it('marks the last section whose top has passed the reading line', () => {
    expect(currentSection([500, 900, 1400], 300)).toBe(0)
    expect(currentSection([-400, 100, 900], 300)).toBe(1)
    expect(currentSection([-900, -400, -100], 300)).toBe(2)
  })
})
