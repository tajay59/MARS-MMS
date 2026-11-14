import type { Filters } from './audit'
import type { AuditRecord, CheckOut } from '@/api/models'
import { onBeforeUnmount, ref, watch } from 'vue'
import { auditApi } from '@/api/audit'
import { ApiError, NetworkError } from '@/api/problem'
import { exportName, toApi } from './audit'

/*
  The audit log's data (PRD AUD-4, AUD-5): a search paged by cursor, the integrity check and
  the CSV export. Everything needs a connection and nothing is kept on the device.
*/

function words (error: unknown, what: string): string {
  if (error instanceof NetworkError) {
    return 'The audit log needs a connection. Connect to the internet and try again.'
  }
  if (error instanceof ApiError && error.status === 422) {
    return error.detail
  }
  return `We couldn’t ${what}. Try again.`
}

export function useAuditLog (filters: () => Filters) {
  const items = ref<AuditRecord[]>([])
  const total = ref(0)
  const over = ref(false)
  const next = ref<number | null>(null)
  const loading = ref(true)
  const loadingMore = ref(false)
  const problem = ref<string | null>(null)
  let controller: AbortController | undefined

  async function load (): Promise<void> {
    controller?.abort()
    controller = new AbortController()
    loading.value = true
    try {
      const page = await auditApi.events(toApi(filters()), controller.signal)
      items.value = page.items
      total.value = page.total
      over.value = page.over_export_limit
      next.value = page.next_cursor
      problem.value = null
    } catch (error) {
      if (!controller.signal.aborted) {
        problem.value = words(error, 'load the audit log')
        items.value = []
      }
    } finally {
      loading.value = false
    }
  }

  async function more (): Promise<void> {
    if (next.value === null || loadingMore.value) {
      return
    }
    loadingMore.value = true
    try {
      const page = await auditApi.events({ ...toApi(filters()), cursor: next.value })
      items.value = [...items.value, ...page.items]
      next.value = page.next_cursor
    } catch (error) {
      problem.value = words(error, 'load more records')
    } finally {
      loadingMore.value = false
    }
  }

  watch(filters, () => void load(), { deep: true, immediate: true })
  onBeforeUnmount(() => controller?.abort())

  return { items, total, over, next, loading, loadingMore, problem, more, reload: load }
}

/** The integrity check: the last result, asking for a new one, and following it until it ends. */
export function useIntegrity () {
  const check = ref<CheckOut | null>(null)
  const problem = ref<string | null>(null)
  const starting = ref(false)
  let timer: ReturnType<typeof setTimeout> | undefined
  let stopped = false

  function follow (): void {
    clearTimeout(timer)
    const current = check.value
    if (!stopped && current && (current.status === 'queued' || current.status === 'running')) {
      timer = setTimeout(async () => {
        try {
          check.value = await auditApi.check(current.id)
        } catch {
          // The next look tries again; a lost answer is not a failed check
        }
        follow()
      }, 2000)
    }
  }

  async function latest (): Promise<void> {
    try {
      check.value = await auditApi.latestCheck()
    } catch (error) {
      // 404 is "no check has finished yet", which is not a problem
      if (!(error instanceof ApiError && error.status === 404)) {
        problem.value = words(error, 'read the last check')
      }
    }
    follow()
  }

  async function start (): Promise<void> {
    starting.value = true
    problem.value = null
    try {
      check.value = await auditApi.verify()
      follow()
    } catch (error) {
      problem.value = words(error, 'start the check')
    } finally {
      starting.value = false
    }
  }

  onBeforeUnmount(() => {
    stopped = true
    clearTimeout(timer)
  })

  return { check, problem, starting, latest, start }
}

/** Saves the search as a CSV file. The file is made on the server and recorded in the chain. */
export async function saveExport (filters: Filters): Promise<{ ok: true } | { ok: false, message: string }> {
  try {
    const { blob, filename } = await auditApi.exportCsv(toApi(filters))
    const href = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = href
    link.download = exportName(filename)
    document.body.append(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(href), 10_000)
    return { ok: true }
  } catch (error) {
    return { ok: false, message: words(error, 'export the audit log') }
  }
}
