import type { OfflineProfile } from './session'
import type { Session } from '@/app/auth/session'
import { forgetOtherUsers, forgetUser } from './cleanup'
import { hasPin, saveOnlineLogin, setPin } from './session'

/*
  What the phone's store does when the session changes (TRD §6.1, §7.6). Called by the session
  store, never by a page. IndexedDB can be missing or blocked (a private window, cleared site
  data): the device store is a convenience for the field, so a failure here is logged and never
  stops a login or a logout.
*/

const STAFF = new Set(['technician', 'admin', 'viewer'])

/** Clients have no offline session (AUTH-12). */
export function hasOfflineSession (roles: readonly string[]): boolean {
  return roles.some(role => STAFF.has(role))
}

/** The profile the phone keeps for the signed-in user: no email, no phone, no token. */
export function profileOf (session: Session): OfflineProfile {
  const { user } = session
  return {
    user_id: user.id,
    name: user.name,
    roles: user.roles,
    org_id: user.org_id,
    theme: user.theme,
    offline_until: Date.parse(session.refreshExpiresAt),
  }
}

/** A login or refresh: another user's prepared data goes, this user's profile stays current. */
export async function rememberLogin (session: Session): Promise<void> {
  const { user } = session
  try {
    await forgetOtherUsers(user.id)
    if (hasOfflineSession(user.roles)) {
      await saveOnlineLogin(profileOf(session))
    }
  } catch (error) {
    console.error('The device store could not be updated', error)
  }
}

/** Logout: prepared data and the PIN go, queued work stays. */
export async function forgetLogout (userId: string): Promise<void> {
  try {
    await forgetUser(userId)
  } catch (error) {
    console.error('The device store could not be cleared', error)
  }
}

/** Sets or changes the signed-in staff member's device PIN (the profile is saved with it). */
export async function savePin (session: Session, pin: string): Promise<void> {
  await setPin(profileOf(session), pin)
}

/** Whether the signed-in user has a PIN on this phone; false where the store is unavailable. */
export async function userHasPin (userId: string): Promise<boolean> {
  try {
    return await hasPin(userId)
  } catch {
    return false
  }
}
