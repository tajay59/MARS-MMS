import { useRegisterSW } from 'virtual:pwa-register/vue'
import { watch } from 'vue'
import { useUpdateStore } from '@/stores/update'

const HOUR = 60 * 60 * 1000

/*
  Registers /sw.js once, from App.vue (pwa skill vite-pwa-vue.md §4). Looks for a new release
  every hour while online and whenever the app comes back to the foreground; a waiting release
  shows the update prompt, and nothing reloads until the user says so.
*/
export function usePwa (): void {
  if (!('serviceWorker' in navigator)) {
    return
  }
  const updates = useUpdateStore()

  const { needRefresh, updateServiceWorker } = useRegisterSW({
    onRegisteredSW (swUrl, registration) {
      if (!registration) {
        return
      }
      const check = async (): Promise<void> => {
        if (registration.installing || !navigator.onLine) {
          return
        }
        // Skip the check when the server is unreachable, so a flaky link doesn't break the worker.
        const response = await fetch(swUrl, { cache: 'no-store', headers: { 'cache-control': 'no-cache' } })
          .catch(() => null)
        if (response?.status === 200) {
          await registration.update()
        }
      }
      setInterval(() => void check(), HOUR)
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
          void check()
        }
      })
    },
    onRegisterError (error) {
      console.error('Service worker registration failed', error)
    },
  })

  watch(needRefresh, waiting => {
    if (waiting) {
      updates.waiting(() => updateServiceWorker(true))
    }
  }, { immediate: true })
}
