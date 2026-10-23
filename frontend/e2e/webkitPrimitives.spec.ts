import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { devices, expect, test, webkit } from '@playwright/test'

/*
  Safari's engine (pwa finding F6): the browser features the offline runner stands on, checked in
  WebKit. The full offline journeys need a service worker and the files host, which Playwright's
  WebKit cannot reach on this stack (it does not resolve `files.mms.localhost`), so the real
  iPhone stays the proof for those. The browser runs with a profile on disk: WebKit's default
  context is private-browsing-like and refuses Blobs in IndexedDB ("Error preparing Blob/File
  data"), which a phone's normal Safari does not. What runs here: Blobs in IndexedDB, Web Locks with
  `ifAvailable`, PBKDF2 at the PIN's cost, BroadcastChannel and the storage estimate.
*/

test('WebKit keeps blobs in IndexedDB, grants one lock at a time and derives a PIN key @webkit @OFF-5 @AUTH-12', async ({ baseURL }) => {
  const context = await webkit.launchPersistentContext(mkdtempSync(join(tmpdir(), 'mms-webkit-')), {
    ...devices['Desktop Safari'], baseURL, ignoreHTTPSErrors: true,
  })
  const page = await context.newPage()
  await page.goto('/login')
  const found = await page.evaluate(async () => {
    const out: Record<string, unknown> = {}

    // A 3 MB file survives a round trip through IndexedDB as a Blob
    const open = indexedDB.open('webkit-check', 1)
    open.addEventListener('upgradeneeded', () => open.result.createObjectStore('blobs'))
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      open.addEventListener('success', () => resolve(open.result))
      open.addEventListener('error', () => reject(open.error))
    })
    const blob = new Blob([new Uint8Array(3 * 1024 * 1024)], { type: 'image/jpeg' })
    await new Promise<void>((resolve, reject) => {
      const request = db.transaction('blobs', 'readwrite').objectStore('blobs').put(blob, 'a')
      request.addEventListener('success', () => resolve())
      request.addEventListener('error', () => reject(request.error))
    })
    const back = await new Promise<Blob>((resolve, reject) => {
      const request = db.transaction('blobs').objectStore('blobs').get('a')
      request.addEventListener('success', () => resolve(request.result as Blob))
      request.addEventListener('error', () => reject(request.error))
    })
    out.blobSize = back.size
    out.blobType = back.type
    db.close()
    indexedDB.deleteDatabase('webkit-check')

    // The sync runner's lock: while one holds it, `ifAvailable` gives the next nothing
    let second: unknown = 'unset'
    await navigator.locks.request('mms-sync-check', { ifAvailable: true }, async first => {
      out.firstGranted = first !== null
      await navigator.locks.request('mms-sync-check', { ifAvailable: true }, lock => {
        second = lock
      })
    })
    out.secondGranted = second !== null

    // The PIN's key derivation at its real cost
    const started = performance.now()
    const material = await crypto.subtle.importKey('raw', new TextEncoder().encode('4729'), 'PBKDF2', false, ['deriveBits'])
    const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', iterations: 310_000, salt: new Uint8Array(16) }, material, 256)
    out.pbkdf2Bytes = bits.byteLength
    out.pbkdf2Ms = Math.round(performance.now() - started)

    out.broadcastChannel = typeof BroadcastChannel === 'function'
    out.storageEstimate = typeof navigator.storage?.estimate === 'function'
    out.storagePersist = typeof navigator.storage?.persist === 'function'
    return out
  })

  await context.close()

  expect(found.blobSize).toBe(3 * 1024 * 1024)
  expect(found.blobType).toBe('image/jpeg')
  expect(found.firstGranted).toBe(true)
  expect(found.secondGranted).toBe(false)
  expect(found.pbkdf2Bytes).toBe(32)
  expect(found.pbkdf2Ms as number).toBeLessThan(5000)
  expect(found.broadcastChannel).toBe(true)
  expect(found.storageEstimate).toBe(true)
  test.info().annotations.push({ type: 'webkit', description: JSON.stringify(found) })
})
