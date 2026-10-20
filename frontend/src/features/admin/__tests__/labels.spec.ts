import type { JobOut, StationSummary } from '@/api/models'
import { describe, expect, it, vi } from 'vitest'
import { isFinished, pagesFor, phoneProblem, pickable, PollGaveUp, pollJob, sheetNote } from '../labels'

function job (status: JobOut['status']): JobOut {
  return { id: 'j', type: 'labels', status, created_at: '2026-10-20T10:00:00Z' }
}

function station (code: string, name: string, country = 'JM'): StationSummary {
  return {
    id: code, code, name, type: null, status: 'operational', owner_org_id: 'o', owner_org_name: 'Org', country,
    time_zone: 'America/Jamaica', region: null, parameters: [], latitude: null, longitude: null,
  }
}

describe('sheet size', () => {
  it('has ten labels to a page', () => {
    expect([1, 10, 11, 200].map(n => pagesFor(n))).toEqual([1, 1, 2, 20])
    expect(sheetNote(3)).toBe('1 page · 10 labels to a page · 98 × 55 mm')
    expect(sheetNote(25)).toBe('3 pages · 10 labels to a page · 98 × 55 mm')
  })
})

describe('phoneProblem', () => {
  it.each(['', ' '.repeat(3), '+1 876 555 0100', '(876) 555-0100', '8765550100'])('accepts %j', value => {
    expect(phoneProblem(value)).toBeNull()
  })

  it.each(['abc', '12', '+1 876 555 0100 ext 5', '1'.repeat(31)])('refuses %j', value => {
    expect(phoneProblem(value)).toMatch(/digits, spaces/)
  })
})

describe('pickable', () => {
  const all = [station('JM-KIN-001', 'Kingston Harbour'), station('JM-MOB-001', 'Montego Bay Airport'), station('TT-POS-001', 'Port of Spain', 'TT')]

  it('filters by search and by country', () => {
    expect(pickable(all, '', null)).toHaveLength(3)
    expect(pickable(all, 'harbour', null).map(s => s.code)).toEqual(['JM-KIN-001'])
    expect(pickable(all, 'mob', null).map(s => s.code)).toEqual(['JM-MOB-001'])
    expect(pickable(all, '', 'TT').map(s => s.code)).toEqual(['TT-POS-001'])
    expect(pickable(all, 'jm', 'TT')).toEqual([])
  })
})

describe('pollJob', () => {
  const noWait = vi.fn(async () => {})

  it('asks again until the job is done', async () => {
    const ask = vi.fn()
      .mockResolvedValueOnce(job('queued'))
      .mockResolvedValueOnce(job('running'))
      .mockResolvedValueOnce(job('done'))
    const result = await pollJob(ask, 'j', { sleep: noWait })
    expect(result.status).toBe('done')
    expect(ask).toHaveBeenCalledTimes(3)
  })

  it('returns a failed job too', async () => {
    expect(isFinished(job('failed'))).toBe(true)
    expect(isFinished(job('running'))).toBe(false)
    const result = await pollJob(vi.fn().mockResolvedValue(job('failed')), 'j', { sleep: noWait })
    expect(result.status).toBe('failed')
  })

  it('asks again after a dropped connection', async () => {
    const ask = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(job('done'))
    expect((await pollJob(ask, 'j', { sleep: noWait })).status).toBe('done')
  })

  it('gives up after the allowed asks, and waits longer each time', async () => {
    const sleep = vi.fn(async (_ms: number) => {})
    await expect(pollJob(vi.fn().mockResolvedValue(job('running')), 'j', { maxAsks: 4, delays: [1, 2], sleep })).rejects.toBeInstanceOf(PollGaveUp)
    expect(sleep.mock.calls.map(c => c[0])).toEqual([1, 2, 2, 2])
  })

  it('stops when the caller aborts', async () => {
    const abort = new AbortController()
    const ask = vi.fn(async () => {
      abort.abort(new DOMException('stop', 'AbortError'))
      throw new Error('aborted')
    })
    await expect(pollJob(ask, 'j', { signal: abort.signal, sleep: noWait })).rejects.toThrow()
    expect(ask).toHaveBeenCalledTimes(1)
  })
})
