import type { Closeouts } from './reports'
import type { ClientReportOut, ReportSummary, RequestDetail } from '@/api/models'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { clientReportsApi } from '@/api/operations'
import { reportsApi } from '@/api/report'
import { closeoutBeingMade, closeoutsOf, isSettling, visitReportsOf } from './reports'

/*
  The reports of one request (PRD RPT-8, CRP-5; W18): the close-out, the newest report of each
  visit and the client reports, read from the report service and operations as this person may
  see them. Nothing is kept on the device. While a PDF is being made the page looks again every
  few seconds, and when the person comes back to the tab.
*/

const LOOK_AGAIN_MS = 8000

export function useRequestReports (detail: () => Pick<RequestDetail, 'id' | 'status' | 'milestones' | 'visits'>) {
  const closeouts = ref<Closeouts>({ current: null, replaced: [] })
  const visitReports = ref<ReportSummary[]>([])
  const clientReports = ref<ClientReportOut[]>([])
  const loaded = ref(false)
  const problem = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | undefined
  let generation = 0

  const pending = computed(() => closeoutBeingMade(detail(), closeouts.value))
  const count = computed(() => (closeouts.value.current ? 1 : 0) + visitReports.value.length + clientReports.value.length)

  function stop (): void {
    clearTimeout(timer)
    timer = undefined
  }

  async function load (): Promise<void> {
    const mine = ++generation
    stop()
    const request = detail()
    try {
      const ended = request.visits.filter(v => v.status === 'ended')
      const [close, visits, own] = await Promise.all([
        reportsApi.list(`request:${request.id}`),
        Promise.all(ended.map(v => reportsApi.list(`visit:${v.id}`))),
        clientReportsApi.list({ request_id: request.id }),
      ])
      if (mine !== generation) {
        return
      }
      closeouts.value = closeoutsOf(close)
      visitReports.value = visitReportsOf(visits.flat())
      clientReports.value = own.items
      problem.value = null
    } catch {
      if (mine === generation) {
        problem.value = 'The reports could not be loaded. Try again.'
      }
    } finally {
      if (mine === generation) {
        loaded.value = true
        if (isSettling(clientReports.value, pending.value)) {
          timer = setTimeout(() => void load(), LOOK_AGAIN_MS)
        }
      }
    }
  }

  function onVisible (): void {
    if (document.visibilityState === 'visible') {
      void load()
    }
  }

  watch(() => detail().id, () => {
    loaded.value = false
    void load()
  }, { immediate: true })

  document.addEventListener('visibilitychange', onVisible)
  onBeforeUnmount(() => {
    generation += 1
    stop()
    document.removeEventListener('visibilitychange', onVisible)
  })

  return { closeouts, visitReports, clientReports, loaded, problem, pending, count, reload: load }
}
