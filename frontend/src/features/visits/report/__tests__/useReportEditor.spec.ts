import type { ReportOut } from '@/api/models'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import { ApiError, NetworkError } from '@/api/http'
import { reportsApi } from '@/api/report'
import { SAVE_AFTER_MS, useReportEditor, wordsFor } from '../editor/useReportEditor'

vi.mock('@/api/report', () => ({
  reportsApi: { get: vi.fn(), edit: vi.fn(), sign: vi.fn(), finalize: vi.fn(), reopen: vi.fn(), preview: vi.fn(), download: vi.fn(), list: vi.fn() },
}))

const get = vi.mocked(reportsApi.get)
const edit = vi.mocked(reportsApi.edit)
const sign = vi.mocked(reportsApi.sign)
const finalize = vi.mocked(reportsApi.finalize)
const reopen = vi.mocked(reportsApi.reopen)

function record (over: Partial<ReportOut> = {}, summary = ''): ReportOut {
  return {
    id: 'r1',
    number: 'VR-2026-0042-02',
    version: 1,
    status: 'draft',
    content_version: 1,
    staff_ids: ['lead'],
    lead_staff_id: 'lead',
    signatures: [],
    pdf: { state: 'none', current: false },
    content: {
      facts: { visit: { staff: [], lead_staff_id: 'lead' }, stations: [{ station_id: 's1', code: 'TST-001', name: 'Hill', elements: [] }] },
      narrative: { summary, recommendations: '', follow_up: '', stations: [{ station_id: 's1', work_performed: '' }] },
      media_selection: [{ station_id: 's1', element_id: 'e', section: 'main', media_id: 'p1', caption: null, in_body: true }],
    },
    ...over,
  } as unknown as ReportOut
}

function conflictWith (current: ReportOut): ApiError {
  return new ApiError(409, { code: 'content_changed', current })
}

function mount () {
  const scope = effectScope()
  const editor = scope.run(() => useReportEditor(ref('r1')))!
  return { editor, stop: () => scope.stop() }
}

async function opened () {
  const mounted = mount()
  await vi.advanceTimersByTimeAsync(0)
  return mounted
}

beforeEach(() => {
  vi.useFakeTimers()
  for (const fn of [get, edit, sign, finalize, reopen]) {
    fn.mockReset()
  }
  get.mockResolvedValue(record())
})
afterEach(() => vi.useRealTimers())

describe('loading', () => {
  it('fills the fields from the draft', async () => {
    get.mockResolvedValue(record({}, 'Funnel replaced.'))
    const { editor, stop } = await opened()
    expect(editor.loaded.value).toBe(true)
    expect(editor.fields.summary).toBe('Funnel replaced.')
    expect(editor.fields.stations.s1).toBe('')
    expect(editor.fields.inBody.p1).toBe(true)
    expect(editor.editable.value).toBe(true)
    stop()
  })

  it('says not found for a report that is not there', async () => {
    get.mockRejectedValue(new ApiError(404, { code: 'not_found' }))
    const { editor, stop } = await opened()
    expect(editor.notFound.value).toBe(true)
    expect(editor.report.value).toBeNull()
    stop()
  })

  it('looks every few seconds while the report is finalizing, then stops', async () => {
    get
      .mockResolvedValueOnce(record({ status: 'finalizing' }))
      .mockResolvedValueOnce(record({ status: 'finalizing' }))
      .mockResolvedValue(record({ status: 'final' }))
    const { editor, stop } = await opened()
    await vi.advanceTimersByTimeAsync(3000)
    await vi.advanceTimersByTimeAsync(3000)
    expect(editor.report.value?.status).toBe('final')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(get).toHaveBeenCalledTimes(3)
    stop()
  })
})

describe('saving', () => {
  it('saves 0.8 s after the last keystroke with the version it read', async () => {
    edit.mockResolvedValue(record({ content_version: 2 }, 'Done.'))
    const { editor, stop } = await opened()
    editor.fields.summary = 'Do'
    editor.touch('summary')
    await vi.advanceTimersByTimeAsync(SAVE_AFTER_MS - 100)
    editor.fields.summary = 'Done.'
    editor.touch('summary')
    await vi.advanceTimersByTimeAsync(SAVE_AFTER_MS - 100)
    expect(edit).not.toHaveBeenCalled()
    expect(editor.saveState.value).toBe('dirty')
    await vi.advanceTimersByTimeAsync(200)
    expect(edit).toHaveBeenCalledTimes(1)
    expect(edit).toHaveBeenCalledWith('r1', { content_version: 1, narrative: { summary: 'Done.' } })
    expect(editor.saveState.value).toBe('saved')
    expect(editor.report.value?.content_version).toBe(2)
    stop()
  })

  it('sends a station, a caption and a placement in the one patch', async () => {
    edit.mockResolvedValue(record({ content_version: 2 }))
    const { editor, stop } = await opened()
    editor.fields.stations.s1 = 'Checked the mast'
    editor.touch('station:s1')
    editor.fields.captions.p1 = 'Looking east'
    editor.touch('caption:p1')
    editor.fields.inBody.p1 = false
    editor.touch('body:p1')
    await vi.advanceTimersByTimeAsync(SAVE_AFTER_MS)
    expect(edit).toHaveBeenCalledWith('r1', {
      content_version: 1,
      narrative: { stations: [{ station_id: 's1', work_performed: 'Checked the mast' }] },
      media_selection: [{ media_id: 'p1', caption: 'Looking east', in_body: false }],
    })
    stop()
  })

  it('keeps what was typed while a save was on its way', async () => {
    let finish: (r: ReportOut) => void = () => {}
    edit.mockReturnValueOnce(new Promise<ReportOut>(resolve => {
      finish = resolve
    }))
    edit.mockResolvedValue(record({ content_version: 3 }, 'Done. And more.'))
    const { editor, stop } = await opened()
    editor.fields.summary = 'Done.'
    editor.touch('summary')
    await vi.advanceTimersByTimeAsync(SAVE_AFTER_MS)
    editor.fields.summary = 'Done. And more.'
    editor.touch('summary')
    finish(record({ content_version: 2 }, 'Done.'))
    await vi.advanceTimersByTimeAsync(0)
    expect(editor.fields.summary).toBe('Done. And more.')
    await vi.advanceTimersByTimeAsync(SAVE_AFTER_MS)
    expect(edit).toHaveBeenLastCalledWith('r1', { content_version: 2, narrative: { summary: 'Done. And more.' } })
    expect(editor.saveState.value).toBe('saved')
    stop()
  })

  it('keeps the text and tries again when the connection is down', async () => {
    edit.mockRejectedValueOnce(new NetworkError(new Error('offline')))
    edit.mockResolvedValue(record({ content_version: 2 }, 'Done.'))
    const { editor, stop } = await opened()
    editor.fields.summary = 'Done.'
    editor.touch('summary')
    await vi.advanceTimersByTimeAsync(SAVE_AFTER_MS)
    expect(editor.saveState.value).toBe('retrying')
    expect(editor.fields.summary).toBe('Done.')
    await vi.advanceTimersByTimeAsync(3000)
    expect(edit).toHaveBeenCalledTimes(2)
    expect(editor.saveState.value).toBe('saved')
    stop()
  })

  it('shows the other editor\'s version and keeps the text that was not saved', async () => {
    edit.mockRejectedValue(conflictWith(record({ content_version: 2 }, 'Written first.')))
    const { editor, stop } = await opened()
    editor.fields.summary = 'Written second.'
    editor.touch('summary')
    await vi.advanceTimersByTimeAsync(SAVE_AFTER_MS)
    expect(editor.fields.summary).toBe('Written first.')
    expect(editor.conflict.value?.lost).toEqual([{ label: 'Summary', text: 'Written second.' }])
    expect(editor.saveState.value).toBe('saved')
    editor.dismissConflict()
    expect(editor.conflict.value).toBeNull()
    stop()
  })

  it('does not offer a draft that stopped being one for editing', async () => {
    get.mockResolvedValue(record({ status: 'finalizing' }))
    const { editor, stop } = await opened()
    editor.fields.summary = 'Late.'
    editor.touch('summary')
    await vi.advanceTimersByTimeAsync(SAVE_AFTER_MS)
    expect(edit).not.toHaveBeenCalled()
    stop()
  })

  it('stops with a message when the server refuses an edit', async () => {
    edit.mockRejectedValue(new ApiError(422, { code: 'too_long' }))
    const { editor, stop } = await opened()
    editor.fields.summary = 'x'
    editor.touch('summary')
    await vi.advanceTimersByTimeAsync(SAVE_AFTER_MS)
    expect(editor.problem.value).toBe('Something went wrong. Try again.')
    expect(editor.saveState.value).toBe('saved')
    expect(edit).toHaveBeenCalledTimes(1)
    stop()
  })
})

describe('signing, finalizing and reopening', () => {
  it('saves what was typed before it signs, and signs the version that was saved', async () => {
    edit.mockResolvedValue(record({ content_version: 2 }, 'Done.'))
    sign.mockResolvedValue(record({ content_version: 2, signatures: [{ id: 's', valid: true } as never] }, 'Done.'))
    const { editor, stop } = await opened()
    editor.fields.summary = 'Done.'
    editor.touch('summary')
    const outcome = await editor.sign('Devon Brown', 'data:image/png;base64,AAAA')
    expect(outcome).toEqual({ ok: true })
    expect(sign).toHaveBeenCalledWith('r1', { content_version: 2, typed_name: 'Devon Brown', image: 'data:image/png;base64,AAAA' })
    expect(editor.report.value?.signatures).toHaveLength(1)
    stop()
  })

  it('does not sign while a change is not saved', async () => {
    edit.mockRejectedValue(new NetworkError(new Error('offline')))
    const { editor, stop } = await opened()
    editor.fields.summary = 'Done.'
    editor.touch('summary')
    const outcome = await editor.sign('Devon Brown', 'x')
    expect(outcome).toMatchObject({ ok: false, kind: 'refused' })
    expect(sign).not.toHaveBeenCalled()
    stop()
  })

  it('shows the changes when the report moved on while signing', async () => {
    sign.mockRejectedValue(conflictWith(record({ content_version: 2 }, 'Changed.')))
    const { editor, stop } = await opened()
    const outcome = await editor.sign('Devon Brown', 'x')
    expect(outcome).toMatchObject({ ok: false, kind: 'changed' })
    expect(editor.fields.summary).toBe('Changed.')
    stop()
  })

  it('reads the record instead of showing an error when a signature was already in', async () => {
    sign.mockRejectedValue(new ApiError(409, { code: 'already_signed' }))
    get.mockResolvedValue(record({ signatures: [{ id: 's', valid: true } as never] }))
    const { editor, stop } = await opened()
    const outcome = await editor.sign('Devon Brown', 'x')
    expect(outcome).toMatchObject({ ok: false, kind: 'already' })
    expect(editor.report.value?.signatures).toHaveLength(1)
    stop()
  })

  it('finalizes, then follows the report until it is final', async () => {
    finalize.mockResolvedValue(record({ status: 'finalizing' }))
    const { editor, stop } = await opened()
    expect(await editor.finalize()).toEqual({ ok: true })
    expect(editor.report.value?.status).toBe('finalizing')
    get.mockResolvedValue(record({ status: 'final' }))
    await vi.advanceTimersByTimeAsync(3000)
    expect(editor.report.value?.status).toBe('final')
    stop()
  })

  it('says why a finalize was refused', async () => {
    finalize.mockRejectedValue(new ApiError(409, { code: 'lead_not_signed' }))
    const { editor, stop } = await opened()
    expect(await editor.finalize()).toEqual({ ok: false, kind: 'refused', message: 'The lead has to sign this version first.' })
    stop()
  })

  it('returns the new draft when an admin reopens', async () => {
    reopen.mockResolvedValue(record({ id: 'r2', version: 2 }))
    const { editor, stop } = await opened()
    const { outcome, next } = await editor.reopen('The priority was missing')
    expect(outcome).toEqual({ ok: true })
    expect(next?.id).toBe('r2')
    expect(reopen).toHaveBeenCalledWith('r1', { reason: 'The priority was missing' })
    stop()
  })
})

describe('wordsFor', () => {
  it('says what went wrong in plain words', () => {
    expect(wordsFor(new NetworkError(new Error('x')))).toBe('Needs a connection. Try again with signal.')
    expect(wordsFor(new ApiError(409, { code: 'not_a_draft' }))).toBe('This report is not a draft any more.')
    expect(wordsFor(new ApiError(403, { code: 'not_lead' }))).toBe('Only the people on this visit, or an admin, can do that.')
    expect(wordsFor(new ApiError(422, { code: 'bad_signature' }))).toBe('The signature could not be used. Clear it and draw it again.')
    expect(wordsFor(new ApiError(500, {}))).toBe('Something went wrong. Try again.')
  })
})
