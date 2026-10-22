import type { VisitOut } from '@/api/models'
import { ref } from 'vue'
import { visitsApi } from '@/api/operations'
import { failureOf } from './failures'

/*
  The visit moves that need no form (start, restore, arrive, depart), shared by the visit page and
  the field page. One at a time: `busy` names the one in progress, for its button's spinner. The
  server decides whether the move is allowed (rules 2 to 5); a refusal that means the visit changed
  under the person reloads it.
*/
export function useVisitMoves (hooks: {
  visit: () => VisitOut | null
  /** The server's new version of the visit, with the sentence to say. */
  changed: (text: string, visit: VisitOut) => void
  say: (text: string) => void
  reload: () => Promise<void>
}) {
  const busy = ref<string | null>(null)

  async function move (key: string, run: () => Promise<VisitOut>, said: string): Promise<void> {
    if (busy.value) {
      return
    }
    busy.value = key
    try {
      hooks.changed(said, await run())
    } catch (error) {
      const result = failureOf(error, 'We couldn’t do that. Try again in a moment.')
      hooks.say(result.message)
      if (result.reload) {
        await hooks.reload()
      }
    } finally {
      busy.value = null
    }
  }

  async function start (): Promise<void> {
    const id = hooks.visit()?.id
    if (id) {
      await move('start', () => visitsApi.start(id), 'Visit started. The request is In progress.')
    }
  }

  async function restore (): Promise<void> {
    const id = hooks.visit()?.id
    if (id) {
      await move('restore', () => visitsApi.restore(id), 'Visit restored to planned.')
    }
  }

  async function station (kind: 'arrive' | 'depart', stationId: string): Promise<void> {
    const id = hooks.visit()?.id
    if (id) {
      await move(`${kind}-${stationId}`, () => visitsApi[kind](id, stationId), kind === 'arrive' ? 'Arrival recorded.' : 'Departure recorded.')
    }
  }

  return { busy, start, restore, station }
}
