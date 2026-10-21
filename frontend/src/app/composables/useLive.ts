import type { EntityUpdate, LiveEvent } from '@/app/realtime/bus'
import { onBeforeUnmount } from 'vue'
import { onLive } from '@/app/realtime/bus'

/*
  Look again when the server says a request changed (PRD NOT-5). The page keeps its place: it
  fetches quietly and swaps the data in, with no skeleton and no jump. A message holds no
  content, so the page asks the API, which applies the person's scope.
*/

/** Calls `handler` for every live event while the component is mounted. */
export function useLive (handler: (event: LiveEvent) => void): void {
  const off = onLive(handler)
  onBeforeUnmount(off)
}

export function isRequestUpdate (event: LiveEvent): event is EntityUpdate {
  return event.entity === 'request'
}

/** `run` at most once per `ms`, after the last call: a burst of changes is one refresh. */
export function settled (run: () => void, ms = 800): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined
  return () => {
    clearTimeout(timer)
    timer = setTimeout(run, ms)
  }
}
