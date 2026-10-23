import type { Me, MePatch, Role } from '@/api/models'
import type { EndReason } from '@/app/auth/session'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi } from '@/api/auth'
import {
  currentSession,
  endSession,
  onSessionChange,
  refreshSession,
  startSession,
  updateUser,
} from '@/app/auth/session'
import { clearRuntimeCaches } from '@/app/pwa/runtimeCaches'
import { forgetLogout, rememberLogin } from '@/offline/account'
import { type OfflineProfile, offlineState } from '@/offline/session'
import { useThemeStore } from './theme'

const STAFF_ROLES: ReadonlySet<Role> = new Set(['technician', 'admin', 'viewer'])

/*
  Who is signed in, for pages and route guards. The token itself stays in app/auth/session.ts.
  The router waits for `bootstrap()` before the first navigation: an app start or reload has no
  access token, only the refresh cookie (TRD §6.1.1, "Returning to the app").
*/
export const useSessionStore = defineStore('session', () => {
  const user = ref<Me | null>(currentSession()?.user ?? null)
  /** Why the last session ended, for the /login banner; cleared by the next login. */
  const endedReason = ref<EndReason | null>(null)
  const ready = ref(false)
  /*
    The app started with no signal and this phone has an offline session: the PIN comes first
    (AUTH-12). `unlockState` says what /unlock shows: the keypad (`ready`), or that offline unlock
    is turned off (`disabled`) or has ended (`expired`).
  */
  const locked = ref(false)
  const unlockState = ref<'ready' | 'disabled' | 'expired' | null>(null)
  const lockedProfile = ref<OfflineProfile | null>(null)
  /** Unlocked with the PIN: the cached profile is signed in, but there is no access token. */
  const offline = ref(false)
  let booting: Promise<void> | null = null

  onSessionChange((session, reason) => {
    const before = user.value?.id
    user.value = session?.user ?? null
    offline.value = false
    if (session) {
      locked.value = false
      endedReason.value = null
      void rememberLogin(session)
      if (session.user.id !== before) {
        // The account's appearance setting wins over this device's (DBD D2).
        useThemeStore().adopt(session.user.theme)
      }
    } else {
      endedReason.value = reason ?? null
      void clearRuntimeCaches()
      if (reason === 'logged_out' && before) {
        // Only a logout clears the phone: an expired or revoked session keeps the prepared data
        void forgetLogout(before)
      }
    }
  })

  const roles = computed<Role[]>(() => (user.value?.roles ?? []) as Role[])
  const isClient = computed(() => roles.value.includes('client'))
  const isAdmin = computed(() => roles.value.includes('admin'))
  const isStaff = computed(() => roles.value.some(r => STAFF_ROLES.has(r)))
  /** Viewers see everything and change nothing (rule 5): action buttons are hidden. */
  const canAct = computed(() => roles.value.some(r => r !== 'viewer'))

  function hasAnyRole (wanted: readonly Role[]): boolean {
    return wanted.some(r => roles.value.includes(r))
  }

  function bootstrap (): Promise<void> {
    booting ??= (async () => {
      if (!currentSession()) {
        // No cookie, a dead one, or no network: the guards treat all three as signed out, except
        // that no network with an offline session on this phone asks for the PIN
        const result = await refreshSession()
        if (result.kind === 'offline') {
          await lockIfOfflineSession()
        }
      }
      ready.value = true
    })()
    return booting
  }

  async function lockIfOfflineSession (): Promise<void> {
    try {
      const state = await offlineState()
      if (state.kind === 'none') {
        return
      }
      locked.value = true
      unlockState.value = state.kind
      lockedProfile.value = state.kind === 'ready' ? state.profile : null
    } catch {
      // No device store (a private window): signed out, as before
    }
  }

  /** The PIN was right: the cached profile is signed in, and the app watches for signal. */
  function unlockOffline (profile: OfflineProfile): void {
    user.value = {
      id: profile.user_id,
      name: profile.name,
      roles: profile.roles,
      org_id: profile.org_id,
      theme: profile.theme ?? 'system',
      email: '',
    } as Me
    locked.value = false
    offline.value = true
    useThemeStore().adopt(profile.theme ?? 'system')
    void reconnect()
  }

  /** The fifth wrong PIN: offline unlock is turned off until the next login with signal. */
  function disableUnlock (): void {
    unlockState.value = 'disabled'
    lockedProfile.value = null
  }

  /**
   * Signal came back (or the app came to the front) while waiting for the PIN or working
   * unlocked: sign in with the refresh cookie, so the token arrives without a screen change. A
   * refresh the server refuses ends the session as usual; a failure to reach it changes nothing.
   */
  async function reconnect (): Promise<void> {
    if ((!offline.value && !locked.value) || !navigator.onLine) {
      return
    }
    await refreshSession()
  }

  if (typeof globalThis.addEventListener === 'function') {
    globalThis.addEventListener('online', () => void reconnect())
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        void reconnect()
      }
    })
  }

  async function login (email: string, password: string): Promise<Me> {
    return startSession(await authApi.login(email, password)).user
  }

  async function acceptInvitation (token: string, password: string): Promise<Me> {
    return startSession(await authApi.acceptInvitation(token, password)).user
  }

  async function logout (): Promise<void> {
    try {
      await authApi.logout()
    } catch {
      // Offline or the server is down: the session still ends on this device
    }
    endSession('logged_out')
  }

  async function updateProfile (patch: MePatch): Promise<Me> {
    const me = await authApi.updateMe(patch)
    updateUser(me)
    return me
  }

  return {
    user,
    endedReason,
    ready,
    locked,
    unlockState,
    lockedProfile,
    offline,
    roles,
    isClient,
    isAdmin,
    isStaff,
    canAct,
    hasAnyRole,
    bootstrap,
    unlockOffline,
    disableUnlock,
    reconnect,
    login,
    acceptInvitation,
    logout,
    updateProfile,
  }
})
