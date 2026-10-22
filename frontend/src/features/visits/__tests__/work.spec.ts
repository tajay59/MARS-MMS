import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from '@/api/problem'
import { actionSentence, actionSentences, checklistSummary, plain, workFailure } from '../work'

function problem (status: number, code: string, detail: string, extra: Record<string, unknown> = {}): ApiError {
  return new ApiError(status, { status, code, detail, ...extra })
}

describe('actionSentence', () => {
  it('says a swap as one sentence with the serials marked', () => {
    const got = actionSentence({
      id: 'a1', action: 'replace', parameter: 'AT', old_serial: 'V-23001', new_serial: 'V-23044', removal_reason: 'faulty',
    })
    expect(plain(got)).toBe('Replaced AT sensor V-23001 with V-23044')
    expect(got.segments.filter(s => s.mono).map(s => s.text)).toEqual(['V-23001', 'V-23044'])
    expect(got.segments.find(s => s.bold)?.text).toBe('AT')
    expect(got.detail).toBe('The old unit went to repair (faulty).')
    expect(got.changesInventory).toBe(true)
  })

  it('adds the technician’s note after why the unit left', () => {
    const got = actionSentence({ id: 'a', action: 'remove', parameter: 'WS', old_serial: 'W-1', removal_reason: 'retired', note: 'Bearing seized.' })
    expect(plain(got)).toBe('Removed WS sensor W-1')
    expect(got.detail).toBe('The unit was retired. Bearing seized.')
  })

  it('says an install, with or without a parameter', () => {
    expect(plain(actionSentence({ id: 'a', action: 'install', parameter: 'RH', new_serial: 'H-9' }))).toBe('Installed RH sensor H-9')
    expect(plain(actionSentence({ id: 'a', action: 'install', new_serial: 'H-9' }))).toBe('Installed sensor H-9')
  })

  it('says the result of a calibration and what it was checked against', () => {
    const got = actionSentence({
      id: 'a', action: 'calibrate', parameter: 'RH', old_serial: 'V-23002',
      calibration: { method: 'field_check', result: 'pass', reference_instrument: { name: 'Fluke 1620A' } },
    })
    expect(plain(got)).toBe('Calibrated RH sensor V-23002: passed (field check)')
    expect(got.detail).toBe('Checked against Fluke 1620A.')
    const adjusted = actionSentence({ id: 'a', action: 'calibrate', old_serial: 'V-1', calibration: { method: 'field_adjust', result: 'adjusted' } })
    expect(plain(adjusted)).toBe('Calibrated sensor V-1: adjusted (field adjustment)')
  })

  it('says cleaning and repair are notes that change nothing in the inventory', () => {
    const got = actionSentence({ id: 'a', action: 'clean', parameter: 'BP', old_serial: 'V-41007' })
    expect(plain(got)).toBe('Cleaned BP sensor V-41007')
    expect(got.changesInventory).toBe(false)
    expect(got.detail).toBe('A note only; the inventory did not change.')
    expect(actionSentence({ id: 'a', action: 'repair', old_serial: 'X', note: 'Reseated the cable.' }).detail).toBe('Reseated the cable.')
  })

  it('never throws on a row it does not know', () => {
    expect(plain(actionSentence({}))).toBe('Sensor work')
    expect(plain(actionSentence({ id: 'a', action: 'replace' }))).toBe('Replaced sensor unknown unit with unknown unit')
  })

  it('turns a record’s actions into sentences in order', () => {
    const rows = [{ id: '1', action: 'install', new_serial: 'A' }, { id: '2', action: 'remove', old_serial: 'B' }]
    expect(actionSentences({ sensor_actions: rows }).map(s => plain(s))).toEqual(['Installed sensor A', 'Removed sensor B'])
  })
})

describe('checklistSummary', () => {
  it('counts what was answered, what had an issue and what was fixed', () => {
    const rows = [{ result: 'ok' }, { result: 'issue' }, { result: 'fixed' }, { result: null }]
    expect(checklistSummary(rows)).toBe('3 of 4 answered, 1 with an issue, 1 fixed')
    expect(checklistSummary([{ result: 'ok' }])).toBe('1 of 1 answered')
    expect(checklistSummary([])).toBe('No checklist')
  })
})

describe('workFailure', () => {
  it('keeps the server’s sentence about the later change and says nothing was saved', () => {
    const got = workFailure(problem(409, 'sensor_changed_later', 'V-23044 has been changed since this action was applied. Correct it on the later visit or ask an admin to change it in the inventory'))
    expect(got.message).toBe('V-23044 has been changed since this action was applied. Correct it on the later visit or ask an admin to change it in the inventory. Nothing was saved, so your record is as you left it.')
    expect(got.reload).toBe(true)
  })

  it('asks for a reload when the record moved on', () => {
    const got = workFailure(problem(409, 'work_changed', 'x'))
    expect(got.message).toContain('Your edits were not saved')
    expect(got.reload).toBe(true)
  })

  it('names the field of a refused entry and says nothing was saved', () => {
    const got = workFailure(problem(422, 'unit_not_at_station', 'V-23002 is not installed at Kingston Harbour. Check the serial', { field: 'sensor_actions' }))
    expect(got.message).toBe('V-23002 is not installed at Kingston Harbour. Check the serial. Nothing was saved.')
    expect(got.field).toBe('sensor_actions')
    expect(got.reload).toBe(false)
  })

  it('explains a locked or unstarted visit and falls back for anything else', () => {
    expect(workFailure(problem(409, 'locked', 'x')).message).toContain('finalized')
    expect(workFailure(problem(409, 'not_started', 'x')).message).toBe('Start the visit first.')
    expect(workFailure(new NetworkError(new Error('offline'))).message).toContain('connection')
    expect(workFailure(new Error('boom')).message).toBe('Could not save the record. Try again.')
    expect(workFailure(problem(500, 'internal', 'x'), 'Try later').message).toBe('Try later')
  })
})
