import type { SummaryType } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { bodyFor, emptyForm, failureWords, firstType, grouped, isActive, lastMonth, lastYear, lookOfJob, periodWords, problemWith, thisYear } from '../summary'

// Summary reports (PRD SUM-1 to SUM-3; AFD J10; decisions W19-8 to W19-10)

function type (key: string, title = key): SummaryType {
  return { type: key, title, description: '', uses_period: true, formats: ['pdf', 'csv'] } as SummaryType
}

describe('grouped', () => {
  it('puts the types in the pane in the order of the groups, leaving out what the server did not send', () => {
    const groups = grouped([type('technician_workload'), type('request_turnaround'), type('station_history'), type('annual_summary')])
    expect(groups.map(g => g.label)).toEqual(['Stations', 'Requests and people', 'Maintenance'])
    expect(groups[1]?.types.map(t => t.type)).toEqual(['request_turnaround', 'technician_workload'])
  })

  it('keeps a type it does not know in Other, so a new report still shows', () => {
    const groups = grouped([type('station_history'), type('a_future_report')])
    expect(groups.at(-1)).toMatchObject({ label: 'Other' })
    expect(groups.at(-1)?.types[0]?.type).toBe('a_future_report')
  })

  it('files the asset, configuration and sensor reports where people look for them', () => {
    const groups = grouped([type('sensor_reliability'), type('station_asset'), type('configuration_history'), type('calibration_due')])
    expect(groups.map(g => [g.label, g.types.map(t => t.type)])).toEqual([
      ['Stations', ['station_asset', 'configuration_history']],
      ['Calibration and sensors', ['calibration_due', 'sensor_reliability']],
    ])
  })

  it('opens on the first type of the first group', () => {
    expect(firstType([type('request_turnaround'), type('network_status')])).toBe('network_status')
    expect(firstType([])).toBeNull()
  })
})

describe('periods', () => {
  it('knows last month, including from January', () => {
    expect(lastMonth(new Date(2026, 9, 28))).toEqual({ from: '2026-09-01', to: '2026-09-30' })
    expect(lastMonth(new Date(2026, 0, 5))).toEqual({ from: '2025-12-01', to: '2025-12-31' })
    expect(lastMonth(new Date(2026, 2, 1))).toEqual({ from: '2026-02-01', to: '2026-02-28' })
  })

  it('knows this year so far and last year', () => {
    expect(thisYear(new Date(2026, 9, 28))).toEqual({ from: '2026-01-01', to: '2026-10-28' })
    expect(lastYear(new Date(2026, 9, 28))).toEqual({ from: '2025-01-01', to: '2025-12-31' })
  })

  it('says a period in words, with the year once when it is the same', () => {
    expect(periodWords('2026-01-01', '2026-09-30')).toBe('1 Jan to 30 Sep 2026')
    expect(periodWords('2025-12-01', '2026-01-31')).toBe('1 Dec 2025 to 31 Jan 2026')
    expect(periodWords(null, null)).toBe('Today')
  })
})

describe('problemWith', () => {
  const form = { ...emptyForm(new Date(2026, 9, 28)), from: '2026-10-01', to: '2026-10-31' }

  it('lets a good period through, and any form for a report with no period', () => {
    expect(problemWith(form, true)).toBeNull()
    expect(problemWith({ ...form, from: '', to: '' }, false)).toBeNull()
  })

  it('says the fix for a missing, backwards or too long period', () => {
    expect(problemWith({ ...form, from: '' }, true)).toBe('Choose the first and last day.')
    expect(problemWith({ ...form, from: '2026-11-01' }, true)).toBe('The last day is before the first day. Swap them.')
    expect(problemWith({ ...form, from: '2020-01-01' }, true)).toBe('Choose a period of up to three years.')
  })
})

describe('bodyFor', () => {
  const form = { ...emptyForm(new Date(2026, 9, 28)), org: 'o-1', country: 'Jamaica', stations: ['s-1'], format: 'csv' as const }

  it('asks for the period, the filters and the format', () => {
    expect(bodyFor('request_turnaround', true, form, false)).toMatchObject({
      type: 'request_turnaround', format: 'csv', from: '2026-09-01', to: '2026-09-30', org_id: 'o-1',
      country: 'Jamaica', station_ids: ['s-1'],
    })
  })

  it('sends a client with no organization, because the server uses theirs', () => {
    expect(bodyFor('client_activity', true, form, true).org_id).toBeNull()
  })

  it('sends no period for a report that has none, and no stations as null', () => {
    const body = bodyFor('network_status', false, { ...form, stations: [] }, false)
    expect(body).toMatchObject({ from: null, to: null, station_ids: null })
  })

  it('sends how far ahead to look only for Calibration due', () => {
    expect(bodyFor('calibration_due', false, { ...form, dueInDays: 60 }, false).due_in_days).toBe(60)
    expect(bodyFor('network_status', false, { ...form, dueInDays: 60 }, false).due_in_days).toBe(30)
  })
})

describe('jobs', () => {
  it('shows a job as waiting, making, ready or failed, and follows only the live ones', () => {
    expect(lookOfJob({ status: 'queued' })).toEqual({ state: 'making', label: 'Waiting' })
    expect(lookOfJob({ status: 'running' })).toEqual({ state: 'making', label: 'Making it' })
    expect(lookOfJob({ status: 'done' })).toEqual({ state: 'ready', label: 'Ready' })
    expect(lookOfJob({ status: 'failed' })).toEqual({ state: 'failed', label: 'Could not be made' })
    expect([isActive({ status: 'queued' }), isActive({ status: 'running' }), isActive({ status: 'done' }), isActive({ status: 'failed' })])
      .toEqual([true, true, false, false])
  })

  it('says why a report failed and what to do', () => {
    expect(failureWords('too_large')).toContain('shorter period')
    expect(failureWords('station_not_found')).toContain('station')
    expect(failureWords(null)).toContain('could not be drawn')
    expect(failureWords('something_new')).toContain('could not be drawn')
  })
})
