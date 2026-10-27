import type { ReportSummary } from '@/api/models'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { ApiError, NetworkError } from '@/api/http'
import { reportsApi } from '@/api/report'
import { useVisitReport, wordsFor } from '../useVisitReport'

vi.mock('@/api/report', () => ({
  reportsApi: { list: vi.fn(), preview: vi.fn(), download: vi.fn() },
}))

const list = vi.mocked(reportsApi.list)
const preview = vi.mocked(reportsApi.preview)

function summary (pdf: Partial<ReportSummary['pdf']> = {}, version = 1): ReportSummary {
  return {
    id: 'r1',
    number: 'VR-2026-0042-02',
    version,
    status: 'draft',
    awaiting_media: 0,
    pdf: { state: 'none', current: false, pages: null, rendered_at: null, error: null, ...pdf },
  } as ReportSummary
}

function mount (enabled = true) {
  const scope = effectScope()
  const state = scope.run(() => useVisitReport(ref('v1'), ref(enabled)))!
  return { state, stop: () => scope.stop() }
}

beforeEach(() => {
  vi.useFakeTimers()
  list.mockReset()
  preview.mockReset()
})
afterEach(() => vi.useRealTimers())

describe('useVisitReport', () => {
  it('keeps looking until the draft has its PDF, then stops', async () => {
    list
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([summary({ state: 'rendering' })])
      .mockResolvedValue([summary({ state: 'ready', current: true, pages: 2 })])
    const { state, stop } = mount()
    await vi.advanceTimersByTimeAsync(0)
    expect(state.report.value).toBeNull()
    expect(state.searching.value).toBe(true)
    await vi.advanceTimersByTimeAsync(5000)
    expect(state.report.value?.pdf.state).toBe('rendering')
    await vi.advanceTimersByTimeAsync(5000)
    expect(state.report.value?.pdf.state).toBe('ready')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(list).toHaveBeenCalledTimes(3)
    stop()
  })

  it('gives up looking for a draft that never appears', async () => {
    list.mockResolvedValue([])
    const { state, stop } = mount()
    await vi.advanceTimersByTimeAsync(5000 * 30)
    expect(state.searching.value).toBe(false)
    const calls = list.mock.calls.length
    await vi.advanceTimersByTimeAsync(60_000)
    expect(list).toHaveBeenCalledTimes(calls)
    stop()
  })

  it('asks for nothing when the visit has not ended', async () => {
    const { stop } = mount(false)
    await vi.advanceTimersByTimeAsync(20_000)
    expect(list).not.toHaveBeenCalled()
    stop()
  })

  it('previews: ready at once, or rendering and then looked at again', async () => {
    list.mockResolvedValue([summary({ state: 'ready', current: false, pages: 1 })])
    const { state, stop } = mount()
    await vi.advanceTimersByTimeAsync(0)
    preview.mockResolvedValueOnce({ state: 'ready', pdf: { state: 'ready', current: true, pages: 1 } } as never)
    expect(await state.preview()).toBe(true)
    expect(state.report.value?.pdf.current).toBe(true)

    preview.mockResolvedValueOnce({ state: 'rendering', pdf: { state: 'rendering', current: false } } as never)
    expect(await state.preview()).toBe(false)
    expect(state.drawing.value).toBe(true)
    list.mockResolvedValue([summary({ state: 'ready', current: true, pages: 1 })])
    await vi.advanceTimersByTimeAsync(5000)
    await nextTick()
    expect(state.drawing.value).toBe(false)
    stop()
  })

  it('says why a preview failed', async () => {
    list.mockResolvedValue([summary()])
    const { state, stop } = mount()
    await vi.advanceTimersByTimeAsync(0)
    preview.mockRejectedValueOnce(new NetworkError('offline'))
    await state.preview()
    expect(state.problem.value).toContain('connection')
    stop()
  })
})

describe('wordsFor', () => {
  it('names the cases a person can act on', () => {
    expect(wordsFor(new ApiError(409, { code: 'draft_not_ready' }))).toContain('still being made')
    expect(wordsFor(new ApiError(403, { code: 'not_attending' }))).toContain('Only the people')
    expect(wordsFor(new ApiError(409, { code: 'not_a_draft' }))).toContain('no longer a draft')
    expect(wordsFor(new Error('x'))).toBe('Something went wrong. Try again.')
  })
})
