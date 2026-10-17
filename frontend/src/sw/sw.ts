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

import { clientsClaim } from 'workbox-core'
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'

declare let self: ServiceWorkerGlobalScope

cleanupOutdatedCaches()
precacheAndRoute(self.__WB_MANIFEST)

registerRoute(new NavigationRoute(createHandlerBoundToURL('/index.html'), {
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
