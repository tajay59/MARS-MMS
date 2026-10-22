import type { BoardElement, VisitOut } from '@/api/models'
import { useVisitMedia } from '@/app/composables/useVisitMedia'

/*
  One upload queue for each visit opened, kept while the Visits page is open (W11-15, kept for the
  board): a file keeps going up when its sheet is closed or the person looks at another visit. When
  a file lands on an element, the boards that show it are told, so the sticky note and an open
  sheet show it without a reload.
*/

type Queue = ReturnType<typeof useVisitMedia>

const queues = new Map<string, Queue>()
const latest = new Map<string, Pick<VisitOut, 'id' | 'stations'>>()
const listeners = new Set<(element: BoardElement) => void>()

export function boardQueue (visit: Pick<VisitOut, 'id' | 'stations'>): Queue {
  latest.set(visit.id, visit)
  let queue = queues.get(visit.id)
  if (!queue) {
    queue = useVisitMedia({
      visit: () => latest.get(visit.id) ?? visit,
      onElement: element => {
        for (const listener of listeners) {
          listener(element)
        }
      },
    })
    queues.set(visit.id, queue)
  }
  return queue
}

/** Hear about every element a finished upload changed. Returns the way to stop. */
export function onElementSaved (listener: (element: BoardElement) => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** The page is going away: stop sending without telling the server. */
export function disposeQueues (): void {
  for (const queue of queues.values()) {
    queue.dispose()
  }
  queues.clear()
  latest.clear()
}
