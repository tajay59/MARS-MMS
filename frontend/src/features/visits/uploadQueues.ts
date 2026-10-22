import type { BoardElement, VisitOut } from '@/api/models'
import { computed, shallowReactive } from 'vue'
import { onSessionChange } from '@/app/auth/session'
import { useVisitMedia } from '@/app/composables/useVisitMedia'

/*
  One upload queue for each visit opened (W11-15, kept for the board): a file keeps going up when
  its sheet is closed, the person looks at another visit or goes to another section. The queues
  belong to the signed-in person, not to a page: they stop when the session ends (logout, an
  expired or revoked session), so the next person on a shared phone never inherits a file. When a
  file lands on an element, the boards that show it are told, so the sticky note and an open
  sheet show it without a reload. Nothing is stored on the device until Phase 5 (OFF-10): a reload
  loses what is still on its way.
*/

type Queue = ReturnType<typeof useVisitMedia>

const queues = shallowReactive(new Map<string, Queue>())
const latest = new Map<string, Pick<VisitOut, 'id' | 'stations'>>()
const listeners = new Set<(element: BoardElement) => void>()
let stopWatching: (() => void) | null = null

export function boardQueue (visit: Pick<VisitOut, 'id' | 'stations'>): Queue {
  stopWatching ??= onSessionChange(session => {
    if (!session) {
      disposeQueues()
    }
  })
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

/** Files on their way from every visit, wherever the person is in the app: for the Sync entry. */
export const uploadsOnTheirWay = computed(() => {
  let sending = 0
  let failed = 0
  for (const queue of queues.values()) {
    for (const item of queue.items) {
      if (item.state === 'failed') {
        failed++
      } else {
        sending++
      }
    }
  }
  return { sending, failed }
})

/** The same, in words for the Sync entry and its page; null when nothing is on its way. */
export const uploadsLabel = computed(() => {
  const { sending, failed } = uploadsOnTheirWay.value
  const files = (n: number) => `${n} ${n === 1 ? 'file' : 'files'}`
  if (sending > 0) {
    return `${files(sending)} uploading`
  }
  return failed > 0 ? `${files(failed)} did not upload` : null
})

/** The person is gone: stop sending without telling the server, and forget every queue. */
export function disposeQueues (): void {
  for (const queue of queues.values()) {
    queue.dispose()
  }
  queues.clear()
  latest.clear()
  stopWatching?.()
  stopWatching = null
}
