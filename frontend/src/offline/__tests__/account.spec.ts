import type { Session } from '@/app/auth/session'
import { afterEach, describe, expect, it } from 'vitest'
import { forgetLogout, hasOfflineSession, rememberLogin } from '../account'
import { db } from '../db'
import { offlineState, setPin } from '../session'

// What a login and a logout do to the phone's store (TRD §6.1, §7.6), through the shared `db`.

const DAY = 24 * 60 * 60 * 1000

function session (id: string, roles: string[], name = 'Devon Brown'): Session {
  return {
    accessToken: 'token',
    expiresAt: Date.now() + 900_000,
    refreshExpiresAt: new Date(Date.now() + (30 * DAY)).toISOString(),
    user: { id, name, roles, org_id: null, theme: 'system' } as Session['user'],
  }
}

afterEach(async () => {
  await Promise.all(db.tables.map(table => table.clear()))
})

describe('hasOfflineSession', () => {
  it('is for staff, not clients', () => {
    expect(hasOfflineSession(['technician'])).toBe(true)
    expect(hasOfflineSession(['viewer'])).toBe(true)
    expect(hasOfflineSession(['client'])).toBe(false)
  })
})

describe('rememberLogin', () => {
  it('keeps a technician’s profile and end date current when they have a PIN here', async () => {
    const first = session('u1', ['technician'])
    await setPin({ user_id: 'u1', name: 'Old', roles: ['technician'], org_id: null, offline_until: 1 }, '4729', { iterations: 1000 })
    await rememberLogin(first)
    const state = await offlineState()
    expect(state.kind === 'ready' && state.profile.name).toBe('Devon Brown')
    expect(state.kind === 'ready' && state.profile.offline_until).toBe(Date.parse(first.refreshExpiresAt))
  })

  it('makes no profile for someone who never set a PIN, and none for a client', async () => {
    await rememberLogin(session('u1', ['technician']))
    await rememberLogin(session('c1', ['client']))
    expect((await offlineState()).kind).toBe('none')
  })

  it('removes the previous user’s prepared data when someone else logs in, and keeps their queued work', async () => {
    await setPin({ user_id: 'u1', name: 'A', roles: ['technician'], org_id: null, offline_until: Date.now() + DAY }, '4729', { iterations: 1000 })
    await db.visits.add({ id: 'v1', user_id: 'u1', data: {} })
    await db.outbox.add({
      op_id: 'o1',
      v: 1,
      user_id: 'u1',
      visit_id: 'v1',
      type: 'visit.start',
      payload: {},
      created_at: '2026-10-22T08:00:00Z',
      attempts: 0,
      status: 'pending',
    })
    await rememberLogin(session('u2', ['technician'], 'Other'))
    expect(await db.visits.count()).toBe(0)
    expect((await offlineState()).kind).toBe('none')
    expect(await db.outbox.count()).toBe(1)
  })
})

describe('forgetLogout', () => {
  it('clears that user’s prepared data and PIN', async () => {
    await setPin({ user_id: 'u1', name: 'A', roles: ['technician'], org_id: null, offline_until: Date.now() + DAY }, '4729', { iterations: 1000 })
    await db.visits.add({ id: 'v1', user_id: 'u1', data: {} })
    await forgetLogout('u1')
    expect(await db.visits.count()).toBe(0)
    expect((await offlineState()).kind).toBe('none')
  })
})
