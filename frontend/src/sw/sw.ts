/// <reference lib="webworker" />

/*
  The AWS-MMS service worker, minimal version (F5, IP W4; TRD §13.3).
  - Precaches the app shell the build emitted, so the app opens with no signal.
  - Answers page navigations with the precached index.html, never API or internal paths.
  - Caches nothing else: API responses, uploads and the files host always go to the network
    (TRD §7.6). Map tiles (F1) and Background Sync arrive in later phases.
  - Waits for the user to accept an update (the prompt), and never calls skipWaiting on its own.
  Keep the file name: the build emits it as /sw.js for ever (pwa skill service-worker.md §3).
*/

import type { PrecacheEntry } from 'workbox-precaching'
import { clientsClaim } from 'workbox-core'
import { cleanupOutdatedCaches, PrecacheController, PrecacheRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'
import { eachLimited, withRetry } from './limit'

declare let self: ServiceWorkerGlobalScope

/*
  Install fetches the precache several files at a time (F14). Workbox's own install fetches one
  file at a time, so on a phone it took the number of files times a round trip: 71 files took
  about 180 s on Android over LTE, and until then the phone had no offline shell. The shell is
  about 1 MB, small enough to fetch in parallel. A file that fails is tried again before the
  install gives up; a failed install leaves no worker, and the app registers again later
  (app/pwa/usePwa.ts).
*/
const PARALLEL = 6
const ATTEMPTS = 3
const RETRY_DELAY_MS = 1000

const manifest: (PrecacheEntry | string)[] = self.__WB_MANIFEST
const precache = new PrecacheController()
precache.addToCacheList(manifest)

async function installPrecache (event: ExtendableEvent): Promise<void> {
  // As PrecacheController.install, but in parallel: a hashed file may come from the HTTP cache
  // (the page has just loaded it), a revisioned one is always fetched again
  await eachLimited(manifest, PARALLEL, async entry => {
    const url = new URL(typeof entry === 'string' ? entry : entry.url, self.location.href).href
    const cacheKey = precache.getCacheKeyForURL(url)
    const revisioned = typeof entry !== 'string' && Boolean(entry.revision)
    await withRetry(async () => {
      const request = new Request(url, {
        integrity: typeof entry === 'string' ? undefined : entry.integrity,
        cache: revisioned ? 'reload' : 'default',
        credentials: 'same-origin',
      })
      await Promise.all(precache.strategy.handleAll({ params: { cacheKey }, request, event }))
    }, ATTEMPTS, RETRY_DELAY_MS)
  })
}

self.addEventListener('install', event => event.waitUntil(installPrecache(event)))
self.addEventListener('activate', event => event.waitUntil(precache.activate(event)))

cleanupOutdatedCaches()
registerRoute(new PrecacheRoute(precache))

registerRoute(new NavigationRoute(precache.createHandlerBoundToURL('/index.html'), {
  denylist: [/^\/api\//, /^\/ws(\/|$)/, /^\/internal\//, /^\/\.well-known\//, /^\/\.releases\//],
}))

self.addEventListener('message', (event: ExtendableMessageEvent) => {
  const data = event.data as { type?: unknown } | null
  if (data?.type === 'SKIP_WAITING') {
    // The user chose Reload in the update prompt.
    void self.skipWaiting()
  }
})

// First install only: take control of the open page so it works offline without a reload.
clientsClaim()
