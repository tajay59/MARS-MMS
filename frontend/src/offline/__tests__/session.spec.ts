import { afterEach, describe, expect, it, vi } from 'vitest'
import { forgetOtherUsers, forgetUser } from '../cleanup'
import { MmsDb } from '../db'
import {
  checkPin,
  clearOfflineSession,
  hasPin,
  MAX_ATTEMPTS,
  type OfflineProfile,
  offlineState,
  saveOnlineLogin,
  setPin,
  unlock,
} from '../session'

// The offline PIN session (AUTH-12, ADR-20) and what a logout or a second user leaves behind
// (TRD §7.6). The iteration count is lowered so the tests stay fast; the app never lowers it.

const FAST = 1000
const NOW = Date.UTC(2026, 9, 22)
const DAY = 24 * 60 * 60 * 1000

const opened: MmsDb[] = []
let n = 0

function open (name = `session-${n++}`): MmsDb {
  const store = new MmsDb(name)
  opened.push(store)
  return store
}

afterEach(async () => {
  for (const store of opened.splice(0)) {
    store.close()
    await store.delete()
  }
})

function profile (over: Partial<OfflineProfile> = {}): OfflineProfile {
  return {
    user_id: 'u1',
    name: 'Devon Brown',
    roles: ['technician'],
    org_id: null,
    offline_until: NOW + (30 * DAY),
    ...over,
  }
}

async function ready (store: MmsDb, pin = '4729'): Promise<void> {
  await setPin(profile(), pin, { store, iterations: FAST })
}

const at = (store: MmsDb) => ({ store, iterations: FAST, now: NOW })

describe('checkPin', () => {
  it.each(['4729', '90817', '350268'])('accepts %s', pin => {
    expect(checkPin(pin)).toBe('ok')
  })

  it.each(['', '123', '1234567', '12a4', '12 34'])('refuses %j as the wrong shape', pin => {
    expect(checkPin(pin)).toBe('format')
  })

  it.each(['0000', '99999', '1234', '4321', '56789', '987654'])('refuses %s as too easy to guess', pin => {
    expect(checkPin(pin)).toBe('weak')
  })
})

describe('setting a PIN', () => {
  it('stores the profile and a verifier, never the PIN', async () => {
    const store = open()
    await ready(store, '4729')
    const stored = (await store.meta.get('offline-session'))!.value as Record<string, unknown>
    expect(JSON.stringify(Object.keys(stored).toSorted())).toContain('verifier')
    expect(JSON.stringify(Object.values(stored).map(v => (v instanceof Uint8Array ? [...v] : v)))).not.toContain('4729')
    expect(await hasPin('u1', store)).toBe(true)
    expect(await hasPin('u2', store)).toBe(false)
  })

  it('uses a different salt each time', async () => {
    const store = open()
    await ready(store)
    const a = ((await store.meta.get('offline-session'))!.value as { salt: Uint8Array }).salt
    await ready(store)
    const b = ((await store.meta.get('offline-session'))!.value as { salt: Uint8Array }).salt
    expect([...a]).not.toEqual([...b])
  })

  it('refuses a PIN that is not allowed', async () => {
    await expect(setPin(profile(), '1111', { store: open(), iterations: FAST })).rejects.toThrow()
  })
})

describe('unlock', () => {
  it('opens with the right PIN and gives the profile', async () => {
    const store = open()
    await ready(store)
    const result = await unlock('4729', at(store))
    expect(result).toEqual({ ok: true, profile: profile() })
  })

  it('says how many tries are left after a wrong PIN', async () => {
    const store = open()
    await ready(store)
    expect(await unlock('1357', at(store))).toEqual({ ok: false, reason: 'wrong', left: 4 })
    expect(await unlock('2468', at(store))).toEqual({ ok: false, reason: 'wrong', left: 3 })
  })

  it('gives the tries back after a right PIN', async () => {
    const store = open()
    await ready(store)
    await unlock('1357', at(store))
    await unlock('4729', at(store))
    expect(await unlock('1357', at(store))).toEqual({ ok: false, reason: 'wrong', left: 4 })
  })

  it('turns offline unlock off on the fifth wrong PIN, even for the right one afterwards', async () => {
    const store = open()
    await ready(store)
    for (let i = 1; i < MAX_ATTEMPTS; i++) {
      expect((await unlock('1357', at(store))).ok).toBe(false)
    }
    expect(await unlock('1357', at(store))).toEqual({ ok: false, reason: 'locked' })
    expect(await unlock('4729', at(store))).toEqual({ ok: false, reason: 'disabled' })
    expect((await offlineState(at(store))).kind).toBe('disabled')
  })

  it('remembers the failures when the app is closed and opened again', async () => {
    const first = open('again')
    await ready(first)
    await unlock('1357', at(first))
    await unlock('1357', at(first))
    first.close()

    const second = open('again')
    expect(await unlock('1357', at(second))).toEqual({ ok: false, reason: 'wrong', left: 2 })
  })

  it('has already counted the try while the check is still running (a killed app gets no free try)', async () => {
    const store = open()
    await ready(store)
    const real = crypto.subtle.deriveBits.bind(crypto.subtle)
    let release: () => void = () => undefined
    const gate = new Promise<void>(resolve => {
      release = resolve
    })
    const spy = vi.spyOn(crypto.subtle, 'deriveBits').mockImplementation(async (...args: Parameters<SubtleCrypto['deriveBits']>) => {
      await gate
      return real(...args)
    })
    try {
      const pending = unlock('4729', at(store))
      await vi.waitFor(async () => {
        expect(((await store.meta.get('offline-session'))!.value as { failed: number }).failed).toBe(1)
      })
      release()
      expect((await pending).ok).toBe(true)
      expect(((await store.meta.get('offline-session'))!.value as { failed: number }).failed).toBe(0)
    } finally {
      spy.mockRestore()
    }
  })

  it('counts every wrong PIN when two checks run at once', async () => {
    const store = open()
    await ready(store)
    const [a, b] = await Promise.all([unlock('1357', at(store)), unlock('2468', at(store))])
    expect(a).toEqual({ ok: false, reason: 'wrong', left: 4 })
    expect(b).toEqual({ ok: false, reason: 'wrong', left: 3 })
  })

  it('refuses when there is no profile or it has run out', async () => {
    const store = open()
    expect(await unlock('4729', at(store))).toEqual({ ok: false, reason: 'none' })
    await ready(store)
    expect(await unlock('4729', { ...at(store), now: NOW + (31 * DAY) })).toEqual({ ok: false, reason: 'expired' })
  })
})

describe('an online login', () => {
  it('clears the lockout and the failures and updates the profile and its end date', async () => {
    const store = open()
    await ready(store)
    for (let i = 0; i < MAX_ATTEMPTS; i++) {
      await unlock('1357', at(store))
    }
    await saveOnlineLogin(profile({ name: 'Devon B.', offline_until: NOW + (60 * DAY) }), store)
    const state = await offlineState(at(store))
    expect(state).toMatchObject({ kind: 'ready', left: MAX_ATTEMPTS })
    expect(state.kind === 'ready' && state.profile.name).toBe('Devon B.')
    expect((await unlock('4729', at(store))).ok).toBe(true)
  })

  it('does nothing for someone who set no PIN here', async () => {
    const store = open()
    await ready(store)
    await saveOnlineLogin(profile({ user_id: 'u2', name: 'Other' }), store)
    const state = await offlineState(at(store))
    expect(state.kind === 'ready' && state.profile.user_id).toBe('u1')
  })
})

describe('logout and a second user (TRD §7.6)', () => {
  async function fill (store: MmsDb): Promise<void> {
    await ready(store)
    for (const user_id of ['u1', 'u2']) {
      await store.bundles.add({
        visit_id: `v-${user_id}`,
        user_id,
        bundle_version: 1,
        prepared_at: '2026-10-22T08:00:00Z',
        ready: true,
        files_total: 1,
        files_done: 1,
        documents: [],
        data: {},
      })
      await store.files.add({
        media_id: `m-${user_id}`,
        visit_id: `v-${user_id}`,
        user_id,
        station_id: null,
        name: 'a.pdf',
        size: 1,
        content_type: 'application/pdf',
        required: false,
        blob: new Blob(['x']),
      })
      await store.visits.add({ id: `v-${user_id}`, user_id, data: {} })
      await store.outbox.add({
        op_id: `op-${user_id}`,
        v: 1,
        user_id,
        visit_id: `v-${user_id}`,
        type: 'visit.start',
        payload: {},
        created_at: '2026-10-22T08:00:00Z',
        attempts: 0,
        status: 'pending',
      })
      await store.blobs.add({
        media_id: `b-${user_id}`,
        user_id,
        owner_ref: 'visit',
        file: new Blob(['x']),
        size: 1,
        sha256: 'abc',
        state: 'pending',
      })
    }
  }

  it('logout deletes that user’s prepared data and PIN and keeps every queued op and file', async () => {
    const store = open()
    await fill(store)
    await forgetUser('u1', store)

    expect((await store.bundles.toArray()).map(r => r.user_id)).toEqual(['u2'])
    expect((await store.files.toArray()).map(r => r.user_id)).toEqual(['u2'])
    expect((await store.visits.toArray()).map(r => r.user_id)).toEqual(['u2'])
    expect((await offlineState(at(store))).kind).toBe('none')
    expect((await store.outbox.toArray()).map(r => r.user_id).toSorted()).toEqual(['u1', 'u2'])
    expect((await store.blobs.toArray()).map(r => r.user_id).toSorted()).toEqual(['u1', 'u2'])
  })

  it('a second user’s login removes the first user’s prepared data and PIN, not their queued work', async () => {
    const store = open()
    await fill(store)
    await forgetOtherUsers('u2', store)

    expect((await store.bundles.toArray()).map(r => r.user_id)).toEqual(['u2'])
    expect((await store.files.toArray()).map(r => r.user_id)).toEqual(['u2'])
    expect((await offlineState(at(store))).kind).toBe('none')
    expect(await store.outbox.count()).toBe(2)
    expect(await store.blobs.count()).toBe(2)
  })

  it('the same user logging in again keeps their PIN and bundles', async () => {
    const store = open()
    await fill(store)
    await forgetOtherUsers('u1', store)
    expect((await offlineState(at(store))).kind).toBe('ready')
    expect(await store.bundles.where('user_id').equals('u1').count()).toBe(1)
  })

  it('clearing the session leaves the tables alone', async () => {
    const store = open()
    await fill(store)
    await clearOfflineSession(store)
    expect(await store.bundles.count()).toBe(2)
  })
})
