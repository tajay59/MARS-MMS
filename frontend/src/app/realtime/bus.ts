/*
  Tells open pages that a request changed (PRD NOT-5). The socket is the only sender; a page
  subscribes for as long as it is open and looks again at what it shows. No Vue here.

  A message holds no content, only which request and what kind of change, so a page never
  trusts it for data: it asks the API, which applies the person's scope (rule 3).
*/

export interface EntityUpdate {
  entity: 'request'
  id: string
  status: string
  kind: 'status' | 'staff' | 'comment'
}

/** A visit changed (W10): which one, the request it belongs to, and its status now. */
export interface VisitUpdate {
  entity: 'visit'
  id: string
  request_id: string
  status: string
}

/** `reconnected`: the socket was away, so anything may have changed. */
export type LiveEvent = EntityUpdate | VisitUpdate | { entity: 'reconnected' }

type Listener = (event: LiveEvent) => void

const listeners = new Set<Listener>()

export function onLive (listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function emitLive (event: LiveEvent): void {
  for (const listener of listeners) {
    try {
      listener(event)
    } catch {
      // One page's trouble is not another's
    }
  }
}

/** For tests. */
export function clearLive (): void {
  listeners.clear()
}
