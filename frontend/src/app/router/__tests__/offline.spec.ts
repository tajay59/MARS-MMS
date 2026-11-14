import type { RouteLocationNormalized } from 'vue-router'
import { describe, expect, it } from 'vitest'
import { opensOffline } from '../index'
import { routes } from '../routes'

// Which pages work with no signal for someone unlocked with the PIN (OFF-10, W13-8).

function to (name: string, params: Record<string, string> = {}): RouteLocationNormalized {
  const route = routes.find(r => r.name === name)!
  return { name, params, meta: route.meta ?? {} } as unknown as RouteLocationNormalized
}

describe('opensOffline', () => {
  it.each(['scan', 'scan-result', 'sync', 'visit-field', 'needs-connection'])('opens %s', name => {
    expect(opensOffline(to(name))).toBe(true)
  })

  it.each(['dashboard', 'requests', 'map', 'queue', 'sensors', 'calibration', 'profile', 'admin-users', 'notifications'])('needs a connection for %s', name => {
    expect(opensOffline(to(name))).toBe(false)
  })

  it('opens a station or a visit by its address, not the list or a form', () => {
    expect(opensOffline(to('stations', { id: '0199-a' }))).toBe(true)
    expect(opensOffline(to('stations'))).toBe(false)
    expect(opensOffline(to('stations', { id: 'new' }))).toBe(false)
    expect(opensOffline(to('stations', { id: '0199-a', mode: 'edit' }))).toBe(false)
    expect(opensOffline(to('visits', { id: '0199-a' }))).toBe(true)
    expect(opensOffline(to('visits'))).toBe(false)
  })
})
