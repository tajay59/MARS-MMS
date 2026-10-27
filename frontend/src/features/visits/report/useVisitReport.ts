import type { ReportSummary } from '@/api/models'
import type { Ref } from 'vue'
import { onBeforeUnmount, ref, watch } from 'vue'
import { ApiError, NetworkError } from '@/api/http'
import { reportsApi } from '@/api/report'
import { isSettling, latest } from './words'

/*
  The newest report of a visit, kept fresh while its draft is being made (W16, RPT-1, RPT-3). The
  report is made on the server once the visit's `end` has synced, so right after the end there may
  be no record yet: look every few seconds, then give up quietly (the page loads it again next
  time). Nothing here is kept on the device: a report is read online only (OFF-10), and the
  ten-minute link is asked for each time it is needed.
*/

const EVERY_MS = 5000
/** About two minutes of looking for a draft that has not appeared. */
const MISSING_TRIES = 24

export interface ReportState {
  report: Ref<ReportSummary | null>
  loaded: Ref<boolean>
  /** No record yet, and still looking for it. */
  searching: Ref<boolean>
  /** A preview was asked for and the PDF is being drawn. */
  drawing: Ref<boolean>
  /** Why the last action failed, in words for the person. */
  problem: Ref<string | null>
  reload: () => Promise<void>
  /** Asks for the PDF; resolves true when the current PDF is ready to open. */
  preview: () => Promise<boolean>
  /** A ten-minute link to the PDF and the file name it is saved under. */
  link: () => Promise<{ url: string, filename: string } | null>
}

export function wordsFor (error: unknown): string {
  if (error instanceof NetworkError) {
    return 'Needs a connection. Try again with signal.'
  }
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return 'Only the people on this visit, or an admin, can draw the preview.'
    }
    if (error.code === 'draft_not_ready') {
      return 'The draft is still being made. Try again in a minute.'
    }
    if (error.code === 'not_a_draft') {
      return 'This report is no longer a draft.'
    }
  }
  return 'Something went wrong. Try again.'
}

export function useVisitReport (visitId: Ref<string>, enabled: Ref<boolean>): ReportState {
  const report = ref<ReportSummary | null>(null)
  const loaded = ref(false)
  const drawing = ref(false)
  const searching = ref(true)
  const problem = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | undefined
  let missing = 0
  let asked = false
  let generation = 0

  function stop (): void {
    clearTimeout(timer)
    timer = undefined
  }

  async function reload (): Promise<void> {
    const mine = generation
    try {
      const found = await reportsApi.list(`visit:${visitId.value}`)
      if (mine !== generation) {
        return
      }
      report.value = latest(found)
      missing = report.value ? 0 : missing + 1
      searching.value = report.value === null && missing < MISSING_TRIES
    } catch {
      // A failed look is not shown: the last answer stays and the next look tries again
    } finally {
      if (mine === generation) {
        loaded.value = true
      }
    }
    if (mine === generation) {
      schedule()
    }
  }

  function schedule (): void {
    stop()
    const waiting = isSettling(report.value) || asked || (report.value === null && missing < MISSING_TRIES)
    if (enabled.value && waiting && document.visibilityState !== 'hidden') {
      timer = setTimeout(() => void reload(), EVERY_MS)
    }
    if (asked && report.value && report.value.pdf.state !== 'rendering') {
      asked = false
      drawing.value = false
    }
  }

  async function preview (): Promise<boolean> {
    const current = report.value
    if (!current) {
      return false
    }
    problem.value = null
    try {
      const answer = await reportsApi.preview(current.id)
      if (answer.state === 'ready') {
        report.value = { ...current, pdf: answer.pdf }
        return true
      }
      asked = true
      drawing.value = true
      report.value = { ...current, pdf: answer.pdf }
      schedule()
      return false
    } catch (error) {
      problem.value = wordsFor(error)
      return false
    }
  }

  async function link (): Promise<{ url: string, filename: string } | null> {
    const current = report.value
    if (!current) {
      return null
    }
    problem.value = null
    try {
      const { url, filename } = await reportsApi.download(current.id)
      return { url, filename }
    } catch (error) {
      problem.value = wordsFor(error)
      return null
    }
  }

  function onVisible (): void {
    if (document.visibilityState === 'visible' && enabled.value) {
      void reload()
    }
  }

  watch([visitId, enabled], ([, on]) => {
    generation += 1
    stop()
    report.value = null
    loaded.value = false
    missing = 0
    searching.value = true
    asked = false
    drawing.value = false
    problem.value = null
    if (on) {
      void reload()
    }
  }, { immediate: true })

  document.addEventListener('visibilitychange', onVisible)
  onBeforeUnmount(() => {
    generation += 1
    stop()
    document.removeEventListener('visibilitychange', onVisible)
  })

  return { report, loaded, searching, drawing, problem, reload, preview, link }
}
