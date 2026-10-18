/*
  Helpers for the worker's install (F14). No worker or DOM globals, so Vitest can run them.
*/

/** Runs `task` on every item, at most `limit` at a time. Rejects with the first failure. */
export async function eachLimited<T> (items: readonly T[], limit: number, task: (item: T) => Promise<void>): Promise<void> {
  let next = 0
  let failed = false
  async function lane (): Promise<void> {
    while (!failed && next < items.length) {
      const item = items[next++] as T
      try {
        await task(item)
      } catch (error) {
        failed = true
        throw error
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, lane))
}

/** Calls `task` up to `attempts` times, waiting `delayMs` between tries; rethrows the last error. */
export async function withRetry<T> (task: () => Promise<T>, attempts: number, delayMs: number): Promise<T> {
  for (let attempt = 1; ; attempt++) {
    try {
      return await task()
    } catch (error) {
      if (attempt >= attempts) {
        throw error
      }
      await new Promise(resolve => setTimeout(resolve, delayMs))
    }
  }
}
