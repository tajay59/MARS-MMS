import { ref } from 'vue'
import { linkProblem } from './reports'

/*
  One PDF sheet for a page that lists several reports (W18). `show` remembers how to ask for the
  chosen report's link; the sheet asks each time it opens, and what went wrong is kept for its
  retry panel. Nothing here is kept beyond the page.
*/

export interface Link { url: string, filename: string }

export function useReportSheet () {
  const opened = ref(false)
  const title = ref('')
  const reason = ref<string | null>(null)
  let ask: (() => Promise<Link>) | null = null

  function show (heading: string, asker: () => Promise<Link>): void {
    title.value = heading
    reason.value = null
    ask = asker
    opened.value = true
  }

  async function fetchLink (): Promise<Link | null> {
    reason.value = null
    try {
      return ask ? await ask() : null
    } catch (error) {
      reason.value = linkProblem(error)
      return null
    }
  }

  return { opened, title, reason, show, fetchLink }
}
