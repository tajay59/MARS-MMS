import type { Dashboard, DashboardView } from '@/api/models'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { NetworkError } from '@/api/problem'
import { reportsApi } from '@/api/report'
import { isRequestUpdate, isVisitUpdate, settled, useLive } from '@/app/composables/useLive'

/*
  The figures of one dashboard (W19-7). They are numbers from the server, so they need a
  connection: offline the page says so and shows no old numbers (the service worker never
  caches an API answer, and nothing here keeps one). They are looked at again every minute
  while the page is shown, when the person comes back to it, when the signal returns, and
  quietly when a request or a visit changes (NOT-5).
*/

const EVERY_MS = 60_000

export type DashboardProblem = 'offline' | 'failed' | null

export function useDashboard (view: () => DashboardView) {
  const data = ref<Dashboard | null>(null)
  const loading = ref(true)
  const problem = ref<DashboardProblem>(null)
  let controller: AbortController | undefined
  let timer: ReturnType<typeof setInterval> | undefined

  async function load (quiet = false): Promise<void> {
    controller?.abort()
    controller = new AbortController()
    try {
      data.value = await reportsApi.dashboard(view(), controller.signal)
      problem.value = null
    } catch (error) {
      if (controller.signal.aborted) {
        return
      }
      // A quiet look that fails keeps the numbers already shown: they were true a minute ago.
      if (!quiet || data.value === null) {
        problem.value = error instanceof NetworkError ? 'offline' : 'failed'
        data.value = null
      }
    } finally {
      loading.value = false
    }
  }

  const refresh = settled(() => {
    void load(true)
  })

  function again (): void {
    if (document.visibilityState === 'visible') {
      void load(true)
    }
  }

  useLive(event => {
    if (event.entity === 'reconnected' || isRequestUpdate(event) || isVisitUpdate(event)) {
      refresh()
    }
  })

  onMounted(() => {
    void load()
    timer = setInterval(again, EVERY_MS)
    document.addEventListener('visibilitychange', again)
    globalThis.addEventListener('online', again)
  })
  onBeforeUnmount(() => {
    controller?.abort()
    clearInterval(timer)
    document.removeEventListener('visibilitychange', again)
    globalThis.removeEventListener('online', again)
  })

  return { data, loading, problem, reload: () => load() }
}
