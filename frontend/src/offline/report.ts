import type { MmsDb } from './db'
import type { OfflineState } from './session'
import type { StorageReport } from './storage'
import type { SyncLogEntry } from './syncLog'
import { describePhone, isStandalone } from '@/app/pwa/platform'
import { db, deviceId } from './db'
import { offlineState } from './session'
import { storageReport } from './storage'
import { formatEntry, readSyncLog } from './syncLog'

/*
  "Copy report" on /sync › This phone (W15-4; pwa skill ios-safari.md §4): the facts a developer
  needs from a phone they cannot hold, as plain text a technician pastes into a message. It holds
  versions, states and counts. It never holds a token, a PIN, the user's name or email, a note, a
  caption, a file name or a whole device ID. Rows for other users on a shared phone are not read.
*/

/** The newest log lines in a report. */
export const LOG_LINES = 50

export interface ReportData {
  time: string
  version: string
  phone: string
  installed: boolean
  online: boolean
  /** True when a service worker controls this page (the next start works with no signal). */
  worker: boolean | null
  storage: StorageReport | null
  pin: string
  /** Last four characters of the device ID, with the first four. */
  device: string
  prepared: { visits: number, files: number }
  queue: { pending: number, conflict: number, failed: number, files: number, bytes: number }
  caches: { names: string[], apiUrls: number } | null
  log: SyncLogEntry[]
}

const MB = 1024 ** 2

function mb (bytes: number): string {
  return `${(bytes / MB).toFixed(bytes < 10 * MB ? 1 : 0)} MB`
}

function yesNo (value: boolean | null): string {
  return value === null ? 'unknown' : (value ? 'yes' : 'no')
}

export function pinWords (state: OfflineState | null): string {
  switch (state?.kind) {
    case 'ready': {
      return `set, valid to ${new Date(state.profile.offline_until).toISOString().slice(0, 10)}`
    }
    case 'disabled': {
      return 'turned off after wrong tries'
    }
    case 'expired': {
      return 'ended'
    }
    case 'none': {
      return 'not set'
    }
    default: {
      return 'unknown'
    }
  }
}

export function formatReport (data: ReportData): string {
  const lines = [
    'MARS-MMS phone report',
    `Time: ${data.time}`,
    `App: version ${data.version}, ${data.installed ? 'installed' : 'in the browser'}`,
    `Phone: ${data.phone}`,
    `Online: ${yesNo(data.online)}`,
    `Service worker in control: ${yesNo(data.worker)}`,
    `Device: ${data.device}`,
    `Offline PIN: ${data.pin}`,
    `Prepared: ${data.prepared.visits} visits, ${data.prepared.files} files`,
    `Waiting: ${data.queue.pending} changes, ${data.queue.files} files (${mb(data.queue.bytes)})`,
    `Needs attention: ${data.queue.conflict} conflicts, ${data.queue.failed} refused`,
  ]
  if (data.storage) {
    lines.push(
      `Storage: ${mb(data.storage.used)} used of ${mb(data.storage.quota)} (${data.storage.percent}%), kept by the browser: ${yesNo(data.storage.persisted)}`,
    )
  } else {
    lines.push('Storage: not reported')
  }
  if (data.caches) {
    lines.push(`Caches: ${data.caches.names.join(', ') || 'none'}; API URLs cached: ${data.caches.apiUrls}`)
  }
  lines.push('', `Sync log (last ${Math.min(data.log.length, LOG_LINES)} of ${data.log.length}, oldest first):`)
  const shown = data.log.slice(-LOG_LINES)
  lines.push(...(shown.length > 0 ? shown.map(entry => formatEntry(entry)) : ['(no runs yet)']))
  return lines.join('\n')
}

/** The names of the caches and how many requests in them are API calls (there must be none: TRD §7.6). */
async function cacheFacts (): Promise<ReportData['caches']> {
  if (typeof caches === 'undefined') {
    return null
  }
  try {
    const names = await caches.keys()
    let apiUrls = 0
    for (const name of names) {
      const cache = await caches.open(name)
      for (const request of await cache.keys()) {
        if (new URL(request.url).pathname.startsWith('/api/')) {
          apiUrls++
        }
      }
    }
    return { names, apiUrls }
  } catch {
    return null
  }
}

/** `version` is the app's (`APP_VERSION`); it is passed in because `app/brand` pulls in image files. */
export async function collectReport (userId: string, version: string, store: MmsDb = db): Promise<ReportData> {
  const [ops, blobs, bundles, files, id, pin, storage, log, cache] = await Promise.all([
    store.outbox.where('user_id').equals(userId).toArray(),
    store.blobs.where('user_id').equals(userId).filter(b => b.state === 'pending' || b.state === 'uploading').toArray(),
    store.bundles.where('user_id').equals(userId).count(),
    store.files.where('user_id').equals(userId).count(),
    deviceId(store).catch(() => ''),
    offlineState({ store }).catch(() => null),
    storageReport().catch(() => null),
    readSyncLog(userId, store),
    cacheFacts(),
  ])
  return {
    time: new Date().toISOString(),
    version,
    phone: describePhone(),
    installed: isStandalone(),
    online: navigator.onLine,
    worker: 'serviceWorker' in navigator ? Boolean(navigator.serviceWorker.controller) : false,
    storage,
    pin: pinWords(pin),
    device: id ? `${id.slice(0, 4)}…${id.slice(-4)}` : 'unknown',
    prepared: { visits: bundles, files },
    queue: {
      pending: ops.filter(op => op.status === 'pending').length,
      conflict: ops.filter(op => op.status === 'conflict').length,
      failed: ops.filter(op => op.status === 'failed').length,
      files: blobs.length,
      bytes: blobs.reduce((sum, b) => sum + b.size, 0),
    },
    caches: cache,
    log,
  }
}
