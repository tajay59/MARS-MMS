/*
  What the browser lets this app keep on the phone (TRD §7.1, risk R4, findings F2 and F3).
  `persist()` is asked for on first field use; the answer is shown, never assumed: Safari may say
  no even for an installed app (WebKit bug 271401).
*/

export const LOW_SPACE_BYTES = 1024 ** 3

export interface StorageReport {
  used: number
  quota: number
  free: number
  percent: number
  persisted: boolean
}

export async function storageReport (): Promise<StorageReport | null> {
  if (!navigator.storage?.estimate) {
    return null
  }
  const { usage = 0, quota = 0 } = await navigator.storage.estimate()
  const persisted = navigator.storage.persisted ? await navigator.storage.persisted() : false
  const free = Math.max(quota - usage, 0)
  return { used: usage, quota, free, percent: quota ? Math.round((usage / quota) * 100) : 0, persisted }
}

/** Asks the browser to keep this app's data. Resolves with the answer, or false where it cannot. */
export async function requestPersistence (): Promise<boolean> {
  try {
    if (!navigator.storage?.persist) {
      return false
    }
    return (await navigator.storage.persisted?.()) || await navigator.storage.persist()
  } catch {
    return false
  }
}

export function isLowSpace (report: StorageReport | null): boolean {
  return report !== null && report.quota > 0 && report.free < LOW_SPACE_BYTES
}
