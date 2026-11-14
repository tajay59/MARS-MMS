import { nextTick, ref } from 'vue'
import { isLocal } from '../local/gateway'

/*
  Starting a visit that is not on the phone (OFF-9, W14 boards "Start visit, not prepared"). With
  signal the person is asked once, before the visit starts: prepare it now, or go ahead and work
  from the server as before. With no signal there is nothing to ask: a visit that was never
  prepared cannot be opened at all, and one that was is started from the phone's copy.
*/
export function useStartCheck (start: () => Promise<void>, visitId: () => string | undefined) {
  const asking = ref(false)

  async function request (): Promise<void> {
    const id = visitId()
    if (!id) {
      return
    }
    if (!navigator.onLine || await isLocal(id)) {
      await start()
      return
    }
    asking.value = true
  }

  async function startAnyway (): Promise<void> {
    asking.value = false
    await start()
  }

  /** Close the question and bring the Prepare for field panel into view: it needs a PIN the first time and a choice of documents. */
  async function prepareNow (): Promise<void> {
    asking.value = false
    await nextTick()
    const panel = document.querySelector<HTMLElement>('section[aria-labelledby="prep-h"]')
    panel?.scrollIntoView({ block: 'center' })
    panel?.querySelector<HTMLElement>('button')?.focus()
  }

  return { asking, request, startAnyway, prepareNow }
}
