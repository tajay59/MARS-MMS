import { liveQuery } from 'dexie'
import { onScopeDispose, shallowRef } from 'vue'

/**
 A Dexie query that runs again when its tables change, in this tab or another. `value` is
 `undefined` until the first answer: show a loading state, not an empty one.
*/
export function useLiveQuery<T> (query: () => T | Promise<T>) {
  const value = shallowRef<T>()
  const error = shallowRef<unknown>()
  const subscription = liveQuery(query).subscribe({
    next: result => {
      value.value = result
    },
    error: reason => {
      error.value = reason
    },
  })
  onScopeDispose(() => subscription.unsubscribe())
  return { value, error }
}
