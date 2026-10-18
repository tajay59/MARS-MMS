import type { ConfigDiff, ConfigVersionOut } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { changeCounts, duplicateName, fileRows, nextVersionNumber, shortHash } from '../configs'

function version (n: number, files: [string, string][]): ConfigVersionOut {
  return {
    id: `v${n}`,
    station_id: 'st-1',
    version: n,
    files: files.map(([filename, sha256], i) => ({ media_id: `m${n}-${i}`, filename, sha256, size_bytes: 100 + i })),
    notes: null,
    visit_id: null,
    created_by: null,
    created_at: '2026-10-14T10:12:00Z',
  }
}

const diff: ConfigDiff = {
  version: 4,
  against: 3,
  added: ['sampling-notes.txt'],
  removed: ['old-interval.cfg'],
  changed: ['logger.cr1x', 'modem-apn.xml'],
  unchanged: ['network.json'],
}

describe('fileRows', () => {
  const v3 = version(3, [['logger.cr1x', 'a1'], ['old-interval.cfg', 'b2'], ['network.json', 'c3'], ['modem-apn.xml', 'd4']])
  const v4 = version(4, [['network.json', 'c3'], ['logger.cr1x', 'a9'], ['sampling-notes.txt', 'e5'], ['modem-apn.xml', 'd8']])

  it('lists changed, added and unchanged files, then those the version dropped', () => {
    const rows = fileRows(v4, v3, diff)
    expect(rows.map(r => [r.filename, r.change])).toEqual([
      ['logger.cr1x', 'changed'],
      ['modem-apn.xml', 'changed'],
      ['sampling-notes.txt', 'added'],
      ['network.json', 'unchanged'],
      ['old-interval.cfg', 'removed'],
    ])
  })

  it('takes a removed file from the earlier version, so the table can say where it was', () => {
    const removed = fileRows(v4, v3, diff).find(r => r.change === 'removed')
    expect(removed?.media_id).toBe('m3-1')
  })

  it('shows every file as unchanged when there is nothing to compare with', () => {
    const rows = fileRows(v4, null, null)
    expect(rows).toHaveLength(4)
    expect(rows.every(r => r.change === 'unchanged')).toBe(true)
  })

  it('counts each kind', () => {
    expect(changeCounts(fileRows(v4, v3, diff))).toEqual({ changed: 2, added: 1, removed: 1, unchanged: 1 })
  })
})

describe('helpers', () => {
  it('numbers the next version after the highest, whatever the order', () => {
    expect(nextVersionNumber([])).toBe(1)
    expect(nextVersionNumber([{ version: 4 }, { version: 3 }])).toBe(5)
    expect(nextVersionNumber([{ version: 2 }, { version: 7 }, { version: 3 }])).toBe(8)
  })

  it('treats two names that differ only in case as the same file', () => {
    expect(duplicateName(['Network.json'], 'network.JSON')).toBe(true)
    expect(duplicateName(['network.json'], 'alerts.csv')).toBe(false)
  })

  it('shortens a checksum to eight characters', () => {
    expect(shortHash('9f2c41ab77d1f3a05ae9022d')).toBe('9f2c41ab')
  })
})
