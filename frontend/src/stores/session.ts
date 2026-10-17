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
  let booting: Promise<void> | null = null

  onSessionChange((session, reason) => {
    const before = user.value?.id
    user.value = session?.user ?? null
    if (session) {
      endedReason.value = null
      if (session.user.id !== before) {
        // The account's appearance setting wins over this device's (DBD D2).
        useThemeStore().adopt(session.user.theme)
      }
    } else {
      endedReason.value = reason ?? null
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
        // No cookie, a dead one, or no network: the guards treat all three as signed out.
        await refreshSession()
      }
      ready.value = true
    })()
    return booting
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
    roles,
    isClient,
    isAdmin,
    isStaff,
    canAct,
    hasAnyRole,
    bootstrap,
    login,
    acceptInvitation,
    logout,
    updateProfile,
  }
})
