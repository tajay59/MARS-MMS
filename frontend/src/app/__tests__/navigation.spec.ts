import { describe, expect, it } from 'vitest'
import { clientSections, sectionOf, sectionsFor, staffSections } from '@/app/navigation'

// The app shell's sections (DBD "The app shell", AFD §5.1)
describe('sectionsFor', () => {
  it('gives admins every staff section, Admin included', () => {
    const keys = sectionsFor(staffSections, ['admin']).map(s => s.key)
    expect(keys).toEqual(['dashboard', 'work', 'stations', 'reports', 'admin'])
  })

  it('hides Admin and the queue from viewers', () => {
    const sections = sectionsFor(staffSections, ['viewer'])
    expect(sections.map(s => s.key)).not.toContain('admin')
    expect(sections.find(s => s.key === 'work')?.items.map(i => i.to)).toEqual(['requests'])
  })

  it('opens a technician\'s Work section on the queue', () => {
    const work = sectionsFor(staffSections, ['technician']).find(s => s.key === 'work')
    expect(work?.items[0]?.to).toBe('queue')
  })

  it('lets every staff role reach Scan, and no client', () => {
    for (const role of ['technician', 'admin', 'viewer'] as const) {
      const routes = sectionsFor(staffSections, [role]).flatMap(s => s.items.map(i => i.to))
      expect(routes).toContain('scan')
    }
    expect(sectionsFor(clientSections, ['client']).flatMap(s => s.items.map(i => i.to))).not.toContain('scan')
  })

  it('keeps client sections free of staff pages', () => {
    const routes = sectionsFor(clientSections, ['client']).flatMap(s => s.items.map(i => i.to))
    expect(routes).not.toContain('scan')
    expect(routes).not.toContain('queue')
    expect(routes).not.toContain('sensors')
    expect(routes.some(r => r.startsWith('admin-'))).toBe(false)
  })
})

describe('sectionOf', () => {
  const admin = sectionsFor(staffSections, ['admin'])

  it('finds the section of a tab', () => {
    expect(sectionOf(admin, 'admin-users')?.key).toBe('admin')
    expect(sectionOf(admin, 'calibration')?.key).toBe('stations')
  })

  it('finds the section of a page that is not a tab', () => {
    expect(sectionOf(admin, 'request-new')?.key).toBe('work')
  })

  it('gives pages outside every section none', () => {
    expect(sectionOf(admin, 'profile')).toBeUndefined()
    expect(sectionOf(admin, undefined)).toBeUndefined()
  })
})
