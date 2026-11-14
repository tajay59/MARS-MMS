import type { MmsDb } from './db'
import { db } from './db'
import { clearOfflineSession } from './session'

/*
  What a phone forgets, and what it never does (TRD §7.6, W13-5).

  On logout or a change of user the app deletes that user's prepared visits, downloaded files,
  working copies, offline profile and PIN. Queued operations and captured media (`outbox`,
  `blobs`) stay, tagged with their `user_id`, and sync only when that user logs in again. No
  function here touches those two tables.
*/

/** Logout: this user's field data goes, their unsynced work stays. */
export async function forgetUser (userId: string, store: MmsDb = db): Promise<void> {
  await store.transaction('rw', [store.bundles, store.files, store.visits, store.meta], async () => {
    await store.bundles.where('user_id').equals(userId).delete()
    await store.files.where('user_id').equals(userId).delete()
    await store.visits.where('user_id').equals(userId).delete()
    await clearOfflineSession(store)
  })
}

/**
 A different user logs in: whoever was here before loses their prepared data and PIN (one profile
 per device), and their queued work stays for them.
*/
export async function forgetOtherUsers (currentUserId: string, store: MmsDb = db): Promise<void> {
  await store.transaction('rw', [store.bundles, store.files, store.visits, store.meta], async () => {
    await store.bundles.where('user_id').notEqual(currentUserId).delete()
    await store.files.where('user_id').notEqual(currentUserId).delete()
    await store.visits.where('user_id').notEqual(currentUserId).delete()
    const profile = (await store.meta.get('offline-session'))?.value as { user_id?: string } | undefined
    if (profile && profile.user_id !== currentUserId) {
      await clearOfflineSession(store)
    }
  })
}
