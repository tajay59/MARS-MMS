import { useRegisterSW } from 'virtual:pwa-register/vue'
import { watch } from 'vue'
import { useUpdateStore } from '@/stores/update'
import { captureInstallPrompt } from './install'

const HOUR = 60 * 60 * 1000
const SW_URL = `${import.meta.env.BASE_URL}sw.js`

/*
  The first install can fail on a bad link (F14): one precache file that still fails after its
  retries fails the install, and the browser drops the worker. Nothing would try again until the
  next page load, so a phone could keep working without an offline shell. Register again when
  the connection returns or the app comes back to the foreground and no worker is installed or
  installing. The prompt for a later release comes with the next start.
*/
export async function ensureWorker (): Promise<void> {
  if (!navigator.onLine) {
    return
  }
  const registration = await navigator.serviceWorker.getRegistration(import.meta.env.BASE_URL)
  if (registration?.active || registration?.installing || registration?.waiting) {
    return
  }
  await navigator.serviceWorker.register(SW_URL, { scope: import.meta.env.BASE_URL }).catch(() => undefined)
}

/*
  Registers /sw.js once, from App.vue (pwa skill vite-pwa-vue.md §4). Looks for a new release
  every hour while online and whenever the app comes back to the foreground; a waiting release
  shows the update prompt, and nothing reloads until the user says so.
*/
export function usePwa (): void {
  // The kill-switch build (`npm run build:kill`, W15-3) ships a worker that unregisters itself: an
  // app that registered it again on every start would be reloaded by it for ever
  if (import.meta.env.MODE === 'kill' || !('serviceWorker' in navigator)) {
    return
  }
  const updates = useUpdateStore()
  captureInstallPrompt()

  window.addEventListener('online', () => void ensureWorker())
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      void ensureWorker()
    }
  })

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
