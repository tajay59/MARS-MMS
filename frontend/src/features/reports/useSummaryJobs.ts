import type { SummaryIn, SummaryJob } from '@/api/models'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { NetworkError } from '@/api/problem'
import { reportsApi } from '@/api/report'
import { isActive } from './summary'

/*
  The person's own summary reports (J10): the list, asking for one, and looking again while one is
  being made. A report is ready in about two minutes (NFR-2), so the page looks every 3 seconds
  while any is waiting or running and stops when none is. Nothing is kept on the device: a
  finished job carries a ten-minute link that acts as a password.
*/

const EVERY_MS = 3000

export function useSummaryJobs () {
  const jobs = ref<SummaryJob[]>([])
  const loading = ref(true)
  const problem = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | undefined
  let stopped = false

  function schedule (): void {
    clearTimeout(timer)
    if (!stopped && jobs.value.some(j => isActive(j))) {
      timer = setTimeout(() => void load(true), EVERY_MS)
    }
  }

  async function load (quiet = false): Promise<void> {
    try {
      jobs.value = await reportsApi.summaryJobs()
      problem.value = null
    } catch (error) {
      if (!quiet) {
        problem.value = error instanceof NetworkError
          ? 'This needs a connection. It will load when you have signal.'
          : 'We couldn’t load your reports. Reload the page to try again.'
      }
    } finally {
      loading.value = false
      schedule()
    }
  }

  /** Asks for a report. The same ask within a minute returns the job already made, so it is put in once. */
  async function start (body: SummaryIn): Promise<SummaryJob> {
    const job = await reportsApi.startSummary(body)
    jobs.value = [job, ...jobs.value.filter(j => j.id !== job.id)]
    schedule()
    return job
  }

  onMounted(() => load())
  onBeforeUnmount(() => {
    stopped = true
    clearTimeout(timer)
  })

  return { jobs, loading, problem, start, reload: () => load() }
}
