import type { FieldBundle } from '@/api/models'
import { afterEach, describe, expect, it } from 'vitest'
import { MmsDb } from '../db'
import { preparedStation, preparedVisit, preparedVisits, stationByToken, storedFiles } from '../prepared'

// Reading what Prepare left on the phone (QR-5, W13-13): newest copy wins, one user only.

const opened: MmsDb[] = []
let n = 0
function open (): MmsDb {
  const store = new MmsDb(`prepared-${n++}`)
  opened.push(store)
  return store
}
afterEach(async () => {
  for (const store of opened.splice(0)) {
    store.close()
    await store.delete()
  }
})

function bundle (stations: { id: string, token: string, code: string }[]): FieldBundle {
  return {
    bundle_version: 1,
    stations: stations.map(s => ({ station: { id: s.id, qr_token: s.token, code: s.code } })),
  } as unknown as FieldBundle
}

async function prepare (store: MmsDb, visitId: string, user: string, at: string, stations: { id: string, token: string, code: string }[]): Promise<void> {
  await store.bundles.put({
    visit_id: visitId, user_id: user, bundle_version: 1, prepared_at: at, ready: true,
    files_total: 0, files_done: 0, documents: [], data: bundle(stations),
  })
}

describe('prepared visits', () => {
  it('lists this user’s visits, newest first, and no one else’s', async () => {
    const store = open()
    await prepare(store, 'v1', 'u1', '2026-10-20T08:00:00Z', [])
    await prepare(store, 'v2', 'u1', '2026-10-22T08:00:00Z', [])
    await prepare(store, 'v3', 'u2', '2026-10-23T08:00:00Z', [])
    expect((await preparedVisits('u1', store)).map(p => p.row.visit_id)).toEqual(['v2', 'v1'])
    expect(await preparedVisit('u1', 'v3', store)).toBeNull()
    expect((await preparedVisit('u1', 'v1', store))?.row.visit_id).toBe('v1')
  })
})

describe('stations from the bundles', () => {
  it('finds a station by its label’s token', async () => {
    const store = open()
    await prepare(store, 'v1', 'u1', '2026-10-20T08:00:00Z', [{ id: 's1', token: 'tok-1', code: 'JM-KIN-001' }])
    const found = await stationByToken('u1', 'tok-1', store)
    expect(found?.station.station.id).toBe('s1')
    expect(found?.prepared.row.visit_id).toBe('v1')
  })

  it('finds nothing for a label that is not on the phone, or belongs to someone else’s bundle', async () => {
    const store = open()
    await prepare(store, 'v1', 'u2', '2026-10-20T08:00:00Z', [{ id: 's1', token: 'tok-1', code: 'JM-KIN-001' }])
    expect(await stationByToken('u1', 'tok-1', store)).toBeNull()
    expect(await stationByToken('u2', 'other', store)).toBeNull()
  })

  it('takes the station from the newest prepared visit that includes it', async () => {
    const store = open()
    await prepare(store, 'old', 'u1', '2026-10-20T08:00:00Z', [{ id: 's1', token: 'tok-old', code: 'OLD' }])
    await prepare(store, 'new', 'u1', '2026-10-22T08:00:00Z', [{ id: 's1', token: 'tok-new', code: 'NEW' }])
    const found = await preparedStation('u1', 's1', store)
    expect(found?.prepared.row.visit_id).toBe('new')
    expect(found?.station.station.code).toBe('NEW')
  })
})

describe('stored files', () => {
  it('lists one visit’s files for this user by media ID', async () => {
    const store = open()
    const file = (visit_id: string, media_id: string, user_id = 'u1') => ({
      media_id, visit_id, user_id, station_id: 's1', name: `${media_id}.pdf`, size: 1,
      content_type: 'application/pdf', required: false, blob: new Blob(['x']),
    })
    await store.files.bulkAdd([file('v1', 'a'), file('v1', 'b'), file('v2', 'c'), file('v1', 'd', 'u2')])
    expect([...(await storedFiles('u1', 'v1', store)).keys()].toSorted()).toEqual(['a', 'b'])
  })
})
