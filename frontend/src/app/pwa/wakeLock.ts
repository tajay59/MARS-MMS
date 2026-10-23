import type { Ref } from 'vue'
import { onScopeDispose, watch } from 'vue'

/*
  Keep the screen on while a sync runs (F12): iOS stops JavaScript when the app is not in front,
  and a sleeping screen does the same. The lock is let go when the sync ends, and asked for again
  if the person comes back to the app while it still runs (the browser drops it when the page is
  hidden). Where the browser has no Screen Wake Lock the page says to keep the app open instead.
*/
export const wakeLockSupported = typeof navigator !== 'undefined' && 'wakeLock' in navigator

export function useWakeLock (wanted: Ref<boolean>): void {
  if (!wakeLockSupported) {
    return
  }
  let sentinel: WakeLockSentinel | null = null

  async function hold (): Promise<void> {
    if (sentinel || document.visibilityState !== 'visible') {
      return
    }
    try {
      sentinel = await navigator.wakeLock.request('screen')
      sentinel.addEventListener('release', () => {
        sentinel = null
      })
    } catch {
      sentinel = null // refused (low battery, no permission): the banner still asks to keep the app open
    }
  }

  async function letGo (): Promise<void> {
    const held = sentinel
    sentinel = null
    await held?.release().catch(() => undefined)
  }

  const onVisible = (): void => {
    if (wanted.value && document.visibilityState === 'visible') {
      void hold()
    }
  }
  document.addEventListener('visibilitychange', onVisible)
  const stop = watch(wanted, on => void (on ? hold() : letGo()), { immediate: true })
  onScopeDispose(() => {
    stop()
    document.removeEventListener('visibilitychange', onVisible)
    void letGo()
  })
}
