import type { MmsDb } from './db'
import { db } from './db'

/*
  The offline field session (ADR-20, AUTH-12, W13-3 to W13-5). A staff member who prepares a visit
  sets a 4 to 6 digit device PIN. The phone keeps, in `meta`, their profile, a PBKDF2 verifier of
  the PIN and `offline_until` (the refresh cookie's expiry). With no signal and no live session,
  the right PIN opens their field data. Never the PIN, never a token: syncing still needs a
  successful refresh.

  The PIN is an access gate, not encryption. Anyone who can copy IndexedDB off the phone can try
  every 4 to 6 digit PIN against the verifier, so the phone's own passcode is the protection of
  data at rest (BSD, R11; pwa skill security.md §2).

  One profile per device: a different user logging in replaces it (`forgetOtherUsers`).
*/

export const PBKDF2_ITERATIONS = 310_000
export const MAX_ATTEMPTS = 5
export const PIN_PATTERN = /^\d{4,6}$/
const KEY = 'offline-session'

/** What the app needs to run its route guards with no token: the profile of the signed-in user. */
export interface OfflineProfile {
  user_id: string
  name: string
  roles: string[]
  org_id: string | null
  theme?: string
  /** Milliseconds since the epoch: when the refresh cookie ends (30 days from the last refresh). */
  offline_until: number
}

interface Stored extends OfflineProfile {
  salt: Uint8Array<ArrayBuffer>
  verifier: Uint8Array<ArrayBuffer>
  iterations: number
  failed: number
  disabled: boolean
}

export type OfflineState
  = | { kind: 'none' }
    | { kind: 'expired' }
    | { kind: 'disabled' }
    | { kind: 'ready', profile: OfflineProfile, left: number }

export type UnlockResult
  = | { ok: true, profile: OfflineProfile }
    | { ok: false, reason: 'none' | 'expired' | 'disabled' }
    | { ok: false, reason: 'wrong', left: number }
    | { ok: false, reason: 'locked' }

export interface Options {
  store?: MmsDb
  /** Tests lower this; the app never does. */
  iterations?: number
  now?: number
}

/** Four or more digits, not all the same and not a plain run (1234, 4321). */
export function checkPin (pin: string): 'ok' | 'format' | 'weak' {
  if (!PIN_PATTERN.test(pin)) {
    return 'format'
  }
  const digits = [...pin].map(Number)
  if (digits.every(d => d === digits[0])) {
    return 'weak'
  }
  const steps = digits.slice(1).map((d, i) => d - digits[i]!)
  if (steps.every(s => s === 1) || steps.every(s => s === -1)) {
    return 'weak'
  }
  return 'ok'
}

async function derive (pin: string, salt: Uint8Array<ArrayBuffer>, iterations: number): Promise<Uint8Array<ArrayBuffer>> {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(pin), 'PBKDF2', false, ['deriveBits'])
  const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt, iterations }, key, 256)
  return new Uint8Array(bits)
}

/** Compares every byte, so the time taken does not say where the first difference was. */
function sameBytes (a: Uint8Array, b: Uint8Array): boolean {
  let diff = a.length ^ b.length
  const n = Math.max(a.length, b.length)
  for (let i = 0; i < n; i++) {
    diff |= (a[i] ?? 0) ^ (b[i] ?? 0)
  }
  return diff === 0
}

async function read (store: MmsDb): Promise<Stored | undefined> {
  return (await store.meta.get(KEY))?.value as Stored | undefined
}

function write (store: MmsDb, stored: Stored): Promise<unknown> {
  return store.meta.put({ key: KEY, value: stored })
}

function profileOf (stored: Stored): OfflineProfile {
  return {
    user_id: stored.user_id,
    name: stored.name,
    roles: stored.roles,
    org_id: stored.org_id,
    theme: stored.theme,
    offline_until: stored.offline_until,
  }
}

/** Sets (or changes) the PIN of the signed-in staff member and keeps their profile. */
export async function setPin (profile: OfflineProfile, pin: string, options: Options = {}): Promise<void> {
  if (checkPin(pin) !== 'ok') {
    throw new Error('The PIN is not allowed')
  }
  const store = options.store ?? db
  const iterations = options.iterations ?? PBKDF2_ITERATIONS
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const verifier = await derive(pin, salt, iterations)
  await write(store, { ...profile, salt, verifier, iterations, failed: 0, disabled: false })
}

/** True when this user has set a PIN on this device. */
export async function hasPin (userId: string, store: MmsDb = db): Promise<boolean> {
  return (await read(store))?.user_id === userId
}

/**
 An online login or refresh by a staff member: if they have a PIN here, keep their profile and
 `offline_until` current and clear the failure count and the lockout ("until the next online
 login", AUTH-12). A different user, or no PIN, changes nothing.
*/
export async function saveOnlineLogin (profile: OfflineProfile, store: MmsDb = db): Promise<void> {
  await store.transaction('rw', store.meta, async () => {
    const stored = await read(store)
    if (stored?.user_id === profile.user_id) {
      await write(store, { ...stored, ...profile, failed: 0, disabled: false })
    }
  })
}

export async function offlineState (options: Options = {}): Promise<OfflineState> {
  const stored = await read(options.store ?? db)
  if (!stored) {
    return { kind: 'none' }
  }
  if (stored.offline_until <= (options.now ?? Date.now())) {
    return { kind: 'expired' }
  }
  if (stored.disabled) {
    return { kind: 'disabled' }
  }
  return { kind: 'ready', profile: profileOf(stored), left: MAX_ATTEMPTS - stored.failed }
}

let queue: Promise<unknown> = Promise.resolve()

/**
 Checks a PIN. The failure is written before the check, then cleared on success, so closing the
 app while the check runs cannot give the person another try. The fifth wrong PIN turns offline
 unlock off until the next online login; the data stays. One check at a time.
*/
export function unlock (pin: string, options: Options = {}): Promise<UnlockResult> {
  const run = queue.then(() => check(pin, options))
  queue = run.catch(() => undefined)
  return run
}

async function check (pin: string, options: Options): Promise<UnlockResult> {
  const store = options.store ?? db
  const state = await offlineState(options)
  if (state.kind !== 'ready') {
    return { ok: false, reason: state.kind }
  }
  const stored = (await read(store))!
  const failed = stored.failed + 1
  await write(store, { ...stored, failed, disabled: failed >= MAX_ATTEMPTS })
  const derived = await derive(pin, stored.salt, stored.iterations)
  if (sameBytes(derived, stored.verifier)) {
    await write(store, { ...stored, failed: 0, disabled: false })
    return { ok: true, profile: profileOf(stored) }
  }
  return failed >= MAX_ATTEMPTS ? { ok: false, reason: 'locked' } : { ok: false, reason: 'wrong', left: MAX_ATTEMPTS - failed }
}

/** Removes the profile and PIN (logout). Data belonging to other tables is `forgetUser`'s. */
export async function clearOfflineSession (store: MmsDb = db): Promise<void> {
  await store.meta.delete(KEY)
}
