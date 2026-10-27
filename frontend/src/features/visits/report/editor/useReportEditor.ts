import type { ReportContentPatch, ReportOut } from '@/api/models'
import type { Ref } from 'vue'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ApiError, NetworkError } from '@/api/http'
import { reportsApi } from '@/api/report'
import { contentOf } from './rules'

/*
  The report editor's state (W17, RPT-2, RPT-4 to RPT-6). Everything here needs a connection
  (OFF-10): nothing is written to the device, and what was typed but not saved yet lives in this
  page's memory only. Text saves 0.8 s after the last keystroke, carrying the `content_version`
  that was read; if someone else saved first (409 `content_changed`) their version is shown and the
  text that was not saved is kept in `conflict` so the person can copy it back. A save that fails
  keeps the text in the box and tries again.
*/

export const SAVE_AFTER_MS = 800
const RETRY_FROM_MS = 3000
const RETRY_UP_TO_MS = 30_000
const FOLLOW_EVERY_MS = 3000
const NARRATIVE_KEYS: ReadonlySet<string> = new Set(['summary', 'recommendations', 'follow_up'])

type NarrativeKey = 'summary' | 'recommendations' | 'follow_up'

function isNarrative (key: string): key is NarrativeKey {
  return NARRATIVE_KEYS.has(key)
}

export type SaveState = 'saved' | 'dirty' | 'saving' | 'retrying'

export interface Fields {
  summary: string
  recommendations: string
  follow_up: string
  /** Work performed, by station id. */
  stations: Record<string, string>
  /** Captions in this report, by media id. */
  captions: Record<string, string>
  inBody: Record<string, boolean>
}

export interface Lost { label: string, text: string }

export type Outcome = { ok: true } | { ok: false, kind: 'changed' | 'already' | 'offline' | 'refused' | 'failed', message: string }

function emptyFields (): Fields {
  return { summary: '', recommendations: '', follow_up: '', stations: {}, captions: {}, inBody: {} }
}

export function wordsFor (error: unknown): string {
  if (error instanceof NetworkError) {
    return 'Needs a connection. Try again with signal.'
  }
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'not_a_draft': {
        return 'This report is not a draft any more.'
      }
      case 'draft_not_ready': {
        return 'The draft is still being made. Try again in a minute.'
      }
      case 'lead_not_signed': {
        return 'The lead has to sign this version first.'
      }
      case 'not_attending':
      case 'not_lead': {
        return 'Only the people on this visit, or an admin, can do that.'
      }
      case 'bad_reason': {
        return 'Give a reason of 5 to 500 characters.'
      }
      case 'bad_name': {
        return 'Type your full name.'
      }
      case 'bad_signature':
      case 'signature_too_large': {
        return 'The signature could not be used. Clear it and draw it again.'
      }
      case 'already_reopened': {
        return 'This report was already reopened.'
      }
      default: {
        if (error.status === 403) {
          return 'You cannot do that.'
        }
      }
    }
  }
  return 'Something went wrong. Try again.'
}

export function useReportEditor (id: Ref<string>) {
  const report = ref<ReportOut | null>(null)
  const loaded = ref(false)
  const notFound = ref(false)
  const fields = reactive<Fields>(emptyFields())
  const saveState = ref<SaveState>('saved')
  const savedAt = ref<Date | null>(null)
  const conflict = ref<{ lost: Lost[] } | null>(null)
  const problem = ref<string | null>(null)
  const busy = ref<'sign' | 'finalize' | 'reopen' | 'preview' | null>(null)

  const dirty = new Set<string>()
  let saveTimer: ReturnType<typeof setTimeout> | undefined
  let followTimer: ReturnType<typeof setTimeout> | undefined
  let retryMs = RETRY_FROM_MS
  let saving: Promise<void> | null = null
  let generation = 0

  const content = computed(() => report.value ? contentOf(report.value) : null)
  const editable = computed(() => report.value?.status === 'draft')

  // --- loading and following ---

  /** Fill the fields from a record; what the person typed and has not saved stays. */
  function adopt (next: ReportOut): void {
    report.value = next
    const c = contentOf(next)
    if (!c) {
      return
    }
    const keep = (key: string): boolean => dirty.has(key)
    if (!keep('summary')) {
      fields.summary = c.narrative.summary
    }
    if (!keep('recommendations')) {
      fields.recommendations = c.narrative.recommendations
    }
    if (!keep('follow_up')) {
      fields.follow_up = c.narrative.follow_up
    }
    for (const s of c.narrative.stations) {
      if (!keep(`station:${s.station_id}`)) {
        fields.stations[s.station_id] = s.work_performed
      }
    }
    for (const s of c.media_selection) {
      if (!keep(`caption:${s.media_id}`)) {
        fields.captions[s.media_id] = s.caption ?? ''
      }
      if (!keep(`body:${s.media_id}`)) {
        fields.inBody[s.media_id] = s.in_body
      }
    }
  }

  async function load (): Promise<void> {
    const mine = generation
    try {
      const found = await reportsApi.get(id.value)
      if (mine !== generation) {
        return
      }
      notFound.value = false
      adopt(found)
    } catch (error) {
      if (mine === generation && error instanceof ApiError && error.status === 404) {
        notFound.value = true
        report.value = null
      }
    } finally {
      if (mine === generation) {
        loaded.value = true
      }
    }
    follow()
  }

  /** While the PDF is being made (finalizing) look every few seconds; otherwise stay quiet. */
  function follow (): void {
    clearTimeout(followTimer)
    if (report.value?.status === 'finalizing' && document.visibilityState !== 'hidden') {
      followTimer = setTimeout(() => void load(), FOLLOW_EVERY_MS)
    }
  }

  function onVisible (): void {
    if (document.visibilityState === 'visible' && dirty.size === 0 && saveState.value === 'saved') {
      void load()
    }
  }

  // --- editing ---

  function touch (key: string): void {
    if (!editable.value) {
      return
    }
    dirty.add(key)
    saveState.value = 'dirty'
    clearTimeout(saveTimer)
    saveTimer = setTimeout(() => void flush(), SAVE_AFTER_MS)
  }

  function patchFor (): { body: ReportContentPatch, sent: Map<string, string | boolean> } | null {
    const current = report.value
    if (!current || dirty.size === 0) {
      return null
    }
    const sent = new Map<string, string | boolean>()
    const narrative: NonNullable<ReportContentPatch['narrative']> = {}
    const stations: { station_id: string, work_performed: string }[] = []
    const selection = new Map<string, { media_id: string, in_body?: boolean, caption?: string | null }>()
    for (const key of dirty) {
      if (isNarrative(key)) {
        narrative[key] = fields[key]
        sent.set(key, fields[key])
      } else if (key.startsWith('station:')) {
        const stationId = key.slice('station:'.length)
        const text = fields.stations[stationId] ?? ''
        stations.push({ station_id: stationId, work_performed: text })
        sent.set(key, text)
      } else {
        const [kind, mediaId] = [key.slice(0, key.indexOf(':')), key.slice(key.indexOf(':') + 1)]
        const entry = selection.get(mediaId) ?? { media_id: mediaId }
        if (kind === 'caption') {
          const caption = fields.captions[mediaId] ?? ''
          entry.caption = caption.trim() === '' ? null : caption
          sent.set(key, caption)
        } else {
          entry.in_body = fields.inBody[mediaId]
          sent.set(key, fields.inBody[mediaId]!)
        }
        selection.set(mediaId, entry)
      }
    }
    if (stations.length > 0) {
      narrative.stations = stations
    }
    const body: ReportContentPatch = { content_version: current.content_version }
    if (Object.keys(narrative).length > 0) {
      body.narrative = narrative
    }
    if (selection.size > 0) {
      body.media_selection = [...selection.values()]
    }
    return { body, sent }
  }

  function valueOf (key: string): string | boolean | undefined {
    if (isNarrative(key)) {
      return fields[key]
    }
    if (key.startsWith('station:')) {
      return fields.stations[key.slice('station:'.length)]
    }
    const mediaId = key.slice(key.indexOf(':') + 1)
    return key.startsWith('caption:') ? fields.captions[mediaId] : fields.inBody[mediaId]
  }

  /** Save what is waiting. Resolves when it is saved, or has failed and will be tried again. */
  async function flush (): Promise<void> {
    clearTimeout(saveTimer)
    if (saving) {
      await saving
    }
    const plan = patchFor()
    if (!plan || !report.value) {
      return
    }
    saveState.value = 'saving'
    const mine = generation
    saving = (async () => {
      try {
        const updated = await reportsApi.edit(report.value!.id, plan.body)
        if (mine !== generation) {
          return
        }
        // Keep what was typed while the save was on its way
        for (const [key, sentValue] of plan.sent) {
          if (valueOf(key) === sentValue) {
            dirty.delete(key)
          }
        }
        retryMs = RETRY_FROM_MS
        problem.value = null
        adopt(updated)
        savedAt.value = new Date()
        if (dirty.size > 0) {
          saveState.value = 'dirty'
          saveTimer = setTimeout(() => void flush(), SAVE_AFTER_MS)
        } else {
          saveState.value = 'saved'
        }
      } catch (error) {
        handleSaveError(error)
      } finally {
        saving = null
      }
    })()
    await saving
  }

  function lostText (): Lost[] {
    const labels: Record<string, string> = { summary: 'Summary', recommendations: 'Recommendations', follow_up: 'Follow-up' }
    const lost: Lost[] = []
    for (const key of dirty) {
      const text = valueOf(key)
      if (typeof text !== 'string' || text.trim() === '') {
        continue
      }
      if (labels[key]) {
        lost.push({ label: labels[key], text })
      } else if (key.startsWith('station:')) {
        const code = content.value?.facts.stations.find(s => s.station_id === key.slice('station:'.length))?.code
        lost.push({ label: code ? `Work performed at ${code}` : 'Work performed', text })
      }
    }
    return lost
  }

  function handleSaveError (error: unknown): void {
    if (error instanceof ApiError && error.status === 409 && error.code === 'content_changed') {
      // Someone else saved first: show their version, keep what was not saved
      const current = error.body.current as ReportOut | undefined
      const lost = lostText()
      dirty.clear()
      conflict.value = lost.length > 0 ? { lost } : null
      if (current) {
        adopt(current)
      } else {
        void load()
      }
      saveState.value = 'saved'
      return
    }
    if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
      // The server refused this edit: show why, and stop trying with it
      problem.value = wordsFor(error)
      dirty.clear()
      saveState.value = 'saved'
      void load()
      return
    }
    // Offline or a server that is busy: keep the text and try again
    saveState.value = 'retrying'
    clearTimeout(saveTimer)
    saveTimer = setTimeout(() => void flush(), retryMs)
    retryMs = Math.min(retryMs * 2, RETRY_UP_TO_MS)
  }

  function onOnline (): void {
    if (saveState.value === 'retrying') {
      retryMs = RETRY_FROM_MS
      void flush()
    }
  }

  // --- actions ---

  async function settled (): Promise<boolean> {
    await flush()
    return dirty.size === 0 && saveState.value === 'saved'
  }

  async function act (kind: NonNullable<typeof busy.value>, run: () => Promise<ReportOut>): Promise<Outcome> {
    busy.value = kind
    problem.value = null
    try {
      adopt(await run())
      follow()
      return { ok: true }
    } catch (error) {
      if (error instanceof NetworkError) {
        return { ok: false, kind: 'offline', message: wordsFor(error) }
      }
      if (error instanceof ApiError && error.code === 'content_changed') {
        const current = error.body.current as ReportOut | undefined
        if (current) {
          adopt(current)
        } else {
          await load()
        }
        return { ok: false, kind: 'changed', message: 'The report changed while you were working. Read the changes, then try again.' }
      }
      if (error instanceof ApiError && error.code === 'already_signed') {
        await load()
        return { ok: false, kind: 'already', message: 'You already signed this version.' }
      }
      const refused = error instanceof ApiError && error.status >= 400 && error.status < 500
      return { ok: false, kind: refused ? 'refused' : 'failed', message: wordsFor(error) }
    } finally {
      busy.value = null
    }
  }

  async function sign (typedName: string, image: string): Promise<Outcome> {
    if (!report.value) {
      return { ok: false, kind: 'failed', message: 'Something went wrong. Try again.' }
    }
    if (!await settled()) {
      return { ok: false, kind: 'refused', message: 'Your changes are not saved yet. Wait for Saved, then sign.' }
    }
    const current = report.value
    return await act('sign', () => reportsApi.sign(current.id, { content_version: current.content_version, typed_name: typedName, image }))
  }

  async function finalize (): Promise<Outcome> {
    if (!report.value) {
      return { ok: false, kind: 'failed', message: 'Something went wrong. Try again.' }
    }
    const current = report.value
    return await act('finalize', () => reportsApi.finalize(current.id))
  }

  /** The new draft is returned so the page can open it. */
  async function reopen (reason: string): Promise<{ outcome: Outcome, next: ReportOut | null }> {
    const current = report.value
    if (!current) {
      return { outcome: { ok: false, kind: 'failed', message: 'Something went wrong. Try again.' }, next: null }
    }
    busy.value = 'reopen'
    try {
      const next = await reportsApi.reopen(current.id, { reason })
      return { outcome: { ok: true }, next }
    } catch (error) {
      return { outcome: { ok: false, kind: error instanceof NetworkError ? 'offline' : 'refused', message: wordsFor(error) }, next: null }
    } finally {
      busy.value = null
    }
  }

  /** A ten-minute link to the PDF: the final one, or the draft as it is now (saved first, drawn if it is not current). */
  async function link (): Promise<{ url: string, filename: string } | null> {
    const current = report.value
    if (!current) {
      return null
    }
    problem.value = null
    try {
      if (current.status === 'draft') {
        if (!await settled()) {
          problem.value = 'Your changes are not saved yet. Wait for Saved, then preview.'
          return null
        }
        const answer = await reportsApi.preview(current.id)
        let pdf = answer.pdf
        for (let tries = 0; answer.state !== 'ready' && pdf.state === 'rendering' && tries < 60; tries++) {
          await new Promise(resolve => setTimeout(resolve, 2000))
          pdf = (await reportsApi.get(current.id)).pdf
        }
        if (pdf.state !== 'ready') {
          problem.value = 'The PDF could not be drawn. Try again.'
          return null
        }
      }
      const { url, filename } = await reportsApi.download(current.id)
      return { url, filename }
    } catch (error) {
      problem.value = wordsFor(error)
      return null
    }
  }

  watch(id, () => {
    generation += 1
    clearTimeout(saveTimer)
    clearTimeout(followTimer)
    dirty.clear()
    Object.assign(fields, emptyFields())
    report.value = null
    loaded.value = false
    conflict.value = null
    problem.value = null
    saveState.value = 'saved'
    void load()
  }, { immediate: true })

  // Closing the tab with text that is not saved yet asks first
  function onLeave (event: BeforeUnloadEvent): void {
    if (saveState.value !== 'saved') {
      event.preventDefault()
    }
  }

  document.addEventListener('visibilitychange', onVisible)
  globalThis.addEventListener('online', onOnline)
  globalThis.addEventListener('beforeunload', onLeave)
  onBeforeUnmount(() => {
    globalThis.removeEventListener('beforeunload', onLeave)
    generation += 1
    clearTimeout(saveTimer)
    clearTimeout(followTimer)
    document.removeEventListener('visibilitychange', onVisible)
    globalThis.removeEventListener('online', onOnline)
  })

  return {
    report, loaded, notFound, fields, content, editable, saveState, savedAt, conflict, problem, busy,
    touch, flush, load, sign, finalize, reopen, link,
    dismissConflict: () => {
      conflict.value = null
    },
  }
}
