/*
  The caches the service worker fills besides the precache (src/sw/sw.ts): map tiles only. They
  hold no personal data, but they show where a person has been looking, so they are emptied when
  the session ends (TRD §7.6, "logout clears runtime caches"; a shared phone).
*/

/** The same name as the worker's route. */
export const TILE_CACHE = 'mms-tiles'

export async function clearRuntimeCaches (): Promise<void> {
  try {
    await globalThis.caches?.delete(TILE_CACHE)
  } catch {
    // No Cache Storage (a private window, an old browser): nothing was kept
  }
}
