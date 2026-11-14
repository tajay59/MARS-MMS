import type { Dashboard } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { barFill, barWidths, count, isAdminView, isClientView, isOpen, isTechnicianView, ownView, toneClass, toneOf, waiting } from '../dashboard'

// The dashboards' rules (PRD SUM-4 to SUM-6; DBD "Dashboards"; decision W19-7)

describe('ownView', () => {
  it('gives each role its own dashboard, and a Viewer the admin one', () => {
    expect(ownView(['admin'])).toBe('admin')
    expect(ownView(['viewer'])).toBe('admin')
    expect(ownView(['technician'])).toBe('technician')
    expect(ownView(['client'])).toBe('client')
  })

  it('takes the most senior role when a person holds more than one', () => {
    expect(ownView(['technician', 'admin'])).toBe('admin')
    expect(ownView([])).toBe('client')
  })
})

describe('toneOf', () => {
  it('colours the edge of a tile only while something needs someone', () => {
    expect(toneOf(3, 'amber')).toBe('amber')
    expect(toneOf(1, 'red')).toBe('red')
    expect(toneOf(0, 'red')).toBe('none')
    expect(toneOf(null, 'amber')).toBe('none')
    expect(toneOf(undefined, 'amber')).toBe('none')
    expect(toneClass.none).toBe('border-l-transparent')
  })
})

describe('barWidths', () => {
  it('draws the largest count full width and the rest in proportion', () => {
    const widths = barWidths([
      { status: 'submitted', count: 5 }, { status: 'approved', count: 4 }, { status: 'reopened', count: 1 },
    ])
    expect(widths).toEqual({ submitted: 100, approved: 80, reopened: 20 })
  })

  it('draws nothing wide when nothing is open, and never divides by zero', () => {
    expect(barWidths([{ status: 'submitted', count: 0 }])).toEqual({ submitted: 0 })
    expect(barWidths([])).toEqual({})
  })

  it('has a bar colour for every open status the server sends', () => {
    for (const status of ['submitted', 'approved', 'assigned', 'scheduled', 'in_progress', 'client_review', 'reopened']) {
      expect(barFill[status]).toMatch(/^bg-on-status-/)
    }
  })
})

describe('counts and waiting', () => {
  it('writes a count for people, and a dash for none yet', () => {
    expect(count(12_403)).toBe('12,403')
    expect(count(0)).toBe('0')
    expect(count(null)).toBe('—')
    expect(count(undefined)).toBe('—')
  })

  it('says how long a draft has waited', () => {
    expect(waiting(0)).toBe('today')
    expect(waiting(1)).toBe('1 day')
    expect(waiting(3)).toBe('3 days')
  })

  it('knows which requests are still open', () => {
    expect(isOpen('client_review')).toBe(true)
    expect(isOpen('reopened')).toBe(true)
    expect(isOpen('closed')).toBe(false)
    expect(isOpen('denied')).toBe(false)
  })
})

describe('narrowing a dashboard by its view', () => {
  const at = '2026-10-28T15:00:00Z'
  const admin = { view: 'admin', as_of: at } as unknown as Dashboard
  const technician = { view: 'technician', as_of: at } as unknown as Dashboard
  const client = { view: 'client', as_of: at } as unknown as Dashboard

  it('tells the three apart', () => {
    expect([isAdminView(admin), isTechnicianView(admin), isClientView(admin)]).toEqual([true, false, false])
    expect([isAdminView(technician), isTechnicianView(technician), isClientView(technician)]).toEqual([false, true, false])
    expect([isAdminView(client), isTechnicianView(client), isClientView(client)]).toEqual([false, false, true])
  })
})
