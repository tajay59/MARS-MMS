import type { Session } from '@/app/auth/session'
import { forgetOtherUsers, forgetUser } from './cleanup'
import { saveOnlineLogin } from './session'

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

/** A login or refresh: another user's prepared data goes, this user's profile stays current. */
export async function rememberLogin (session: Session): Promise<void> {
  const { user } = session
  try {
    await forgetOtherUsers(user.id)
    if (hasOfflineSession(user.roles)) {
      await saveOnlineLogin({
        user_id: user.id,
        name: user.name,
        roles: user.roles,
        org_id: user.org_id,
        theme: user.theme,
        offline_until: Date.parse(session.refreshExpiresAt),
      })
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
