import type { Result } from '@/offline/sync'
import { reactive } from 'vue'
import { onSessionChange } from '@/app/auth/session'
import { runSync } from '@/offline/sync'
import { appDeps } from '@/offline/syncDeps'
import { useSessionStore } from '@/stores/session'
import { adoptApplied } from './store'

/*
  The sync runner as the app uses it (TRD §7.3; W14-11): the real session, `/sync` and uploads
  from `offline/syncDeps.ts`, plus what the phone does with each answer (`adoptApplied`). It runs
  when the app starts, when the connection returns, when the app comes back to the front, every
  five minutes while open, after each local change and on "Sync now". Overlaps are harmless: the
  Web Lock `mms-sync` lets one run at a time.
*/

export const FIVE_MINUTES = 5 * 60_000
const SOON_MS = 300

export const syncStatus = reactive<{ running: boolean, last: Result | null, at: number | null }>({
  running: false, last: null, at: null,
})

let soon: ReturnType<typeof setTimeout> | undefined
let started = false

function signedIn (): string | null {
  const session = useSessionStore()
  // Unlocked with the PIN and no token yet: nothing can be sent until the real session returns
  return session.user && !session.offline ? session.user.id : null
}

/** Run now. `force` ignores the backoff ("Sync now"). `trigger` is what the sync log records. */
export async function syncNow (force = true, trigger = force ? 'manual' : 'auto'): Promise<Result | null> {
  const userId = signedIn()
  if (!userId || !navigator.onLine) {
    return null
  }
  syncStatus.running = true
  try {
    const result = await runSync(userId, { ...appDeps, onApplied: (op, answer) => adoptApplied(op, answer) }, { force, trigger })
    syncStatus.last = result
    syncStatus.at = Date.now()
    return result
  } finally {
    syncStatus.running = false
  }
}

/** A change was just made: send it in a moment, together with whatever else is waiting. */
export function requestSync (): void {
  clearTimeout(soon)
  soon = setTimeout(() => void syncNow(false, 'change').catch(() => undefined), SOON_MS)
}

/** Start the triggers. Safe to call more than once. */
export function startSyncTriggers (): void {
  if (started || typeof globalThis.addEventListener !== 'function') {
    return
  }
  started = true
  const kick = (trigger: string) => () => void syncNow(false, trigger).catch(() => undefined)
  globalThis.addEventListener('online', kick('online'))
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      kick('visible')()
    }
  })
  onSessionChange(session => {
    if (session) {
      kick('login')()
    }
  })
  setInterval(kick('timer'), FIVE_MINUTES)
  setTimeout(kick('start'), 1500) // the app has just started: the session is usually ready by now
}
