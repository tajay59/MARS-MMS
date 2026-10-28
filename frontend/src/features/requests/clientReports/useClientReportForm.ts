import type { Model, Pieces, SaveState } from './clientReport'
import type { ClientReportOut, ClientReportPatch, RequestDetail } from '@/api/models'
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { clientReportsApi, requestsApi } from '@/api/operations'
import { NetworkError } from '@/api/problem'
import { newId } from '@/app/ids'
import { emptyModel, failureWords, isEmptyPatch, modelOf, patchOf, submitProblem } from './clientReport'

/*
  The draft of /requests/:id/client-reports/new (PRD CRP-1 to CRP-4; AFD J9; W18-9, W18-10). The
  draft is made on the server as soon as a kind is chosen (the files are uploaded for it), and every
  change is saved 0.8 seconds after the person stops typing, one save at a time, each carrying the
  `version` it was made from. Nothing is kept on the device: text that has not been saved stays in
  the page, and a failed save is tried again until it goes. A submitted report cannot change.
*/

const SAVE_AFTER_MS = 800
const RETRY_AFTER_MS = 5000

export function useClientReportForm (requestId: () => string) {
  const request = ref<RequestDetail | null>(null)
  const report = ref<ClientReportOut | null>(null)
  const model = reactive<Model>(emptyModel([]))
  const saveState = ref<SaveState>('idle')
  const savedAt = ref<Date | null>(null)
  const problem = ref<string | null>(null)
  const notice = ref<string | null>(null)
  const loaded = ref(false)
  const missing = ref(false)
  const gone = ref(false)
  const sending = ref(false)
  const sent = ref(false)
  let baseline: Model = emptyModel([])
  let timer: ReturnType<typeof setTimeout> | undefined
  let chain: Promise<unknown> = Promise.resolve()
  let alive = true

  function adopt (doc: ClientReportOut): void {
    report.value = doc
    baseline = modelOf(doc)
  }

  function fill (next: Model): void {
    model.title = next.title
    model.reportDate = next.reportDate
    model.stationIds = [...next.stationIds]
    model.summary = next.summary
    model.observations = { ...next.observations }
    model.notes = next.notes
  }

  async function loadRequest (): Promise<void> {
    try {
      request.value = await requestsApi.get(requestId())
    } catch {
      missing.value = true
    }
  }

  /** Start on a draft that already exists (Continue draft). */
  async function open (reportId: string): Promise<void> {
    await loadRequest()
    if (request.value) {
      try {
        const doc = await clientReportsApi.get(reportId)
        if (doc.status !== 'draft' || !doc.can_edit) {
          gone.value = true
        } else {
          adopt(doc)
          fill(baseline)
        }
      } catch {
        missing.value = true
      }
    }
    loaded.value = true
  }

  async function prepare (): Promise<void> {
    await loadRequest()
    loaded.value = true
  }

  /** Make the draft when the person has chosen what kind it is. */
  async function begin (kind: ClientReportOut['kind']): Promise<boolean> {
    const found = request.value
    if (!found) {
      return false
    }
    problem.value = null
    try {
      const doc = await clientReportsApi.create({
        id: newId(), request_id: found.id, kind, title: '', station_ids: found.stations.map(s => s.id),
      })
      adopt(doc)
      fill(baseline)
      return true
    } catch (error) {
      problem.value = failureWords(error).text
      return false
    }
  }

  function stopTimer (): void {
    clearTimeout(timer)
    timer = undefined
  }

  function later (ms: number): void {
    stopTimer()
    timer = setTimeout(() => void flush(), ms)
  }

  /** Save what changed. Safe to call at any time: one save runs at a time and the next waits. */
  function flush (extra: Omit<ClientReportPatch, 'version'> = {}): Promise<boolean> {
    stopTimer()
    const run = async (): Promise<boolean> => {
      const current = report.value
      if (!current || current.status !== 'draft' || !alive) {
        return true
      }
      const patch = { ...patchOf(baseline, model, current.kind), ...extra }
      if (isEmptyPatch(patch)) {
        return true
      }
      saveState.value = 'saving'
      try {
        const doc = await clientReportsApi.update(current.id, { ...patch, version: current.version })
        report.value = doc
        // What was sent is now the server's; what was typed since is still in `model`
        baseline = modelOf(doc)
        saveState.value = 'saved'
        savedAt.value = new Date()
        problem.value = null
        return true
      } catch (error) {
        const failure = failureWords(error)
        if (error instanceof NetworkError) {
          saveState.value = 'retrying'
          later(RETRY_AFTER_MS)
          return false
        }
        saveState.value = 'idle'
        if (failure.stale) {
          const doc = await clientReportsApi.get(current.id).catch(() => null)
          if (doc) {
            adopt(doc)
            fill(baseline)
            notice.value = failure.text
          }
        } else if (failure.gone) {
          gone.value = true
        }
        problem.value = failure.stale ? null : failure.text
        return false
      }
    }
    chain = chain.then(run, run)
    return chain as Promise<boolean>
  }

  /** The PDF of a PDF report: the file media has checked, or none. */
  function setPdf (mediaId: string | null): Promise<boolean> {
    return flush({ media_id: mediaId })
  }

  /** The pictures of a form, in order: the ones media has checked. */
  function setImages (ids: string[]): Promise<boolean> {
    return flush({ image_ids: ids })
  }

  function problemFor (pieces: Pieces): { field: string, text: string } | null {
    return report.value ? submitProblem(report.value.kind, model, pieces) : null
  }

  /** Send it. Nothing changes it afterwards (CRP-4). */
  async function submit (): Promise<boolean> {
    const current = report.value
    if (!current) {
      return false
    }
    sending.value = true
    problem.value = null
    try {
      if (!await flush()) {
        return false
      }
      adopt(await clientReportsApi.submit(current.id))
      sent.value = true
      return true
    } catch (error) {
      const failure = failureWords(error)
      problem.value = failure.text
      if (failure.gone) {
        gone.value = true
      }
      return false
    } finally {
      sending.value = false
    }
  }

  watch(model, () => {
    if (report.value?.status === 'draft') {
      later(SAVE_AFTER_MS)
    }
  }, { deep: true })

  onBeforeUnmount(() => {
    // One last try for what was typed just before the person left
    void flush().finally(() => {
      alive = false
    })
    stopTimer()
  })

  return {
    request, report, model, saveState, savedAt, problem, notice, loaded, missing, gone, sending, sent,
    prepare, open, begin, flush, setPdf, setImages, problemFor, submit,
  }
}
