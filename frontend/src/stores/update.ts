import { defineStore } from 'pinia'
import { ref } from 'vue'

/*
  "A new version is ready" (pwa skill service-worker.md §3; F9). Two sources:
  - the service worker installed a new release and is waiting (usePwa sets `waiting`);
  - a lazy route failed to load because a deploy replaced its chunk (the router calls chunkFailed).
  Never applied without the user’s say-so: no silent reloads.
*/
export const useUpdateStore = defineStore('update', () => {
  const visible = ref(false)
  /** Accepts the waiting worker; set by usePwa when one is waiting. */
  let applyWorker: (() => Promise<void>) | null = null
  /** Where the failed navigation was going, so Reload lands there. */
  let target: string | null = null

  function waiting (apply: () => Promise<void>): void {
    applyWorker = apply
    visible.value = true
  }

  function chunkFailed (path: string): void {
    target = path
    visible.value = true
  }

  async function reload (): Promise<void> {
    visible.value = false
    if (applyWorker) {
      // The worker takes control, then every open tab reloads (vite-plugin-pwa prompt mode).
      await applyWorker()
      return
    }
    if (target) {
      window.location.assign(target)
      return
    }
    window.location.reload()
  }

  function later (): void {
    visible.value = false
  }

  return { visible, waiting, chunkFailed, reload, later }
})
