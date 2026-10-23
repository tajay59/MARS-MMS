import type { LocalBlob, MmsDb } from './db'
import { newId } from '@/app/ids'
import { db } from './db'
import { sha256Hex } from './hash'

/*
  The storage check (risk R4, finding F3, W13 exit check on an iPhone): put photos and videos into
  the phone's store, restart the phone, and read every one back. They are test files in `blobs`
  with the state `diagnostic`, tied to the person, and are never uploaded: the sync of W14 must
  skip that state. No Vue here.
*/

export const OWNER_REF = 'storage-check'
export const MAX_FILES = 60

export interface Summary {
  photos: number
  videos: number
  other: number
  bytes: number
}

export interface Verdict {
  checked: number
  matching: number
  /** Names of files that are gone or whose bytes changed. */
  failed: string[]
  at: number
}

const NAMES = 'storage-check-names'

function rows (userId: string, store: MmsDb): Promise<LocalBlob[]> {
  return store.blobs.where('state').equals('diagnostic').filter(b => b.user_id === userId && b.owner_ref === OWNER_REF).toArray()
}

export function summarize (list: readonly Pick<LocalBlob, 'file' | 'size'>[]): Summary {
  const summary: Summary = { photos: 0, videos: 0, other: 0, bytes: 0 }
  for (const item of list) {
    summary.bytes += item.size
    const type = item.file.type
    if (type.startsWith('image/')) {
      summary.photos += 1
    } else if (type.startsWith('video/')) {
      summary.videos += 1
    } else {
      summary.other += 1
    }
  }
  return summary
}

export async function stored (userId: string, store: MmsDb = db): Promise<Summary> {
  return summarize(await rows(userId, store))
}

/** Adds files (up to 60 in all), fingerprinting each as it goes. Returns how many were added. */
export async function addFiles (
  userId: string, files: readonly File[], onEach?: (done: number, total: number) => void, store: MmsDb = db,
): Promise<number> {
  const room = Math.max(0, MAX_FILES - (await rows(userId, store)).length)
  const taking = files.slice(0, room)
  let done = 0
  for (const file of taking) {
    // Hash first, outside the transaction (a hash is not a database call)
    const sha256 = await sha256Hex(file)
    const media_id = newId()
    await store.blobs.put({
      media_id, user_id: userId, owner_ref: OWNER_REF, file, size: file.size, sha256, state: 'diagnostic',
    })
    await store.meta.put({ key: `${NAMES}:${media_id}`, value: file.name })
    done += 1
    onEach?.(done, taking.length)
  }
  return taking.length
}

async function matches (item: LocalBlob): Promise<boolean> {
  return item.file.size === item.size && await sha256Hex(item.file) === item.sha256
}

/** Reads every stored test file again and compares its fingerprint with the one taken on the way in. */
export async function verify (
  userId: string, onEach?: (done: number, total: number) => void, store: MmsDb = db, now: number = Date.now(),
): Promise<Verdict> {
  const list = await rows(userId, store)
  const failed: string[] = []
  let done = 0
  for (const item of list) {
    const ok = await matches(item).catch(() => false)
    if (!ok) {
      const name = (await store.meta.get(`${NAMES}:${item.media_id}`))?.value
      failed.push(typeof name === 'string' ? name : item.media_id)
    }
    done += 1
    onEach?.(done, list.length)
  }
  return { checked: list.length, matching: list.length - failed.length, failed, at: now }
}

export async function clear (userId: string, store: MmsDb = db): Promise<void> {
  const list = await rows(userId, store)
  await store.transaction('rw', store.blobs, store.meta, async () => {
    for (const item of list) {
      await store.blobs.delete(item.media_id)
      await store.meta.delete(`${NAMES}:${item.media_id}`)
    }
  })
}
