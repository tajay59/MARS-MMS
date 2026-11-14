import type { Notice } from './review'
import type { ClientReportOut, ReportSummary, RequestDetail } from '@/api/models'
import { computed, onBeforeUnmount, ref } from 'vue'
import { clientReportsApi, requestsApi } from '@/api/operations'
import { ApiError } from '@/api/problem'
import { reportsApi } from '@/api/report'
import { answerFailure, noticeFor, reviewState } from './review'

/*
  The state of /requests/:id/review (PRD REQ-12 to REQ-14; AFD J8; W18-2, W18-6). The page reads
  the request, each ended visit's final report and the organization's client reports, and keeps the
  `review_started_at` it read: an answer names it (`reviewing`), so a client never signs a review
  that has since begun again. Answering needs a connection and nothing is kept on the device; the
  drawing and the reason live in the dialogs' memory until the server has answered. Sending the
  same answer twice is safe on the server, so a lost reply is answered by asking again.
*/

export interface VisitReportRow {
  visitId: string
  ref: string
  report: ReportSummary | null
}

export function useReview (requestId: () => string) {
  const detail = ref<RequestDetail | null>(null)
  const loaded = ref(false)
  const missing = ref(false)
  const visitReports = ref<VisitReportRow[]>([])
  const clientReports = ref<ClientReportOut[]>([])
  const busy = ref<'accept' | 'reject' | null>(null)
  const failure = ref<Notice | null>(null)
  const answered = ref<'accepted' | 'rejected' | null>(null)
  let generation = 0

  const state = computed(() => detail.value ? reviewState(detail.value) : null)
  const notice = computed(() => state.value ? noticeFor(state.value) : null)
  const open = computed(() => state.value?.kind === 'open')

  async function load (): Promise<void> {
    const mine = ++generation
    try {
      const found = await requestsApi.get(requestId())
      const ended = found.visits.filter(v => v.status === 'ended')
      const [rows, own] = await Promise.all([
        Promise.all(ended.map(async v => ({
          visitId: v.id, ref: v.ref,
          report: (await reportsApi.list(`visit:${v.id}`)).find(r => r.status === 'final') ?? null,
        }))),
        clientReportsApi.list({ request_id: found.id }),
      ])
      if (mine !== generation) {
        return
      }
      detail.value = found
      visitReports.value = rows
      clientReports.value = own.items.filter(r => r.status === 'submitted')
      missing.value = false
    } catch (error) {
      if (mine === generation && error instanceof ApiError && (error.status === 404 || error.status === 422)) {
        missing.value = true
      } else if (mine === generation && !detail.value) {
        failure.value = answerFailure(error)
      }
    } finally {
      if (mine === generation) {
        loaded.value = true
      }
    }
  }

  /** Run one answer; returns true when the server took it. */
  async function answer (kind: 'accept' | 'reject', send: (request: RequestDetail) => Promise<RequestDetail>): Promise<boolean> {
    const current = detail.value
    if (!current?.review_started_at) {
      return false
    }
    busy.value = kind
    failure.value = null
    try {
      detail.value = await send(current)
      answered.value = kind === 'accept' ? 'accepted' : 'rejected'
      return true
    } catch (error) {
      failure.value = answerFailure(error)
      if (failure.value.reload) {
        await load()
      }
      return false
    } finally {
      busy.value = null
    }
  }

  function accept (name: string, image: string, comment: string): Promise<boolean> {
    return answer('accept', request => requestsApi.accept(request.id, {
      reviewing: request.review_started_at as string, typed_name: name, image,
      comment: comment || null, attestation_accepted: true,
    }))
  }

  function reject (reason: string): Promise<boolean> {
    return answer('reject', request => requestsApi.reject(request.id, {
      reviewing: request.review_started_at as string, reason,
    }))
  }

  function onVisible (): void {
    if (document.visibilityState === 'visible' && !busy.value && !answered.value) {
      void load()
    }
  }

  document.addEventListener('visibilitychange', onVisible)
  onBeforeUnmount(() => {
    generation += 1
    document.removeEventListener('visibilitychange', onVisible)
  })

  return { detail, loaded, missing, visitReports, clientReports, busy, failure, answered, state, notice, open, load, accept, reject }
}
