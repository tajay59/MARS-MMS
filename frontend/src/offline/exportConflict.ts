import type { LocalBlob } from './db'

/*
  Export for a conflict (ADR-18, TRD §7.4; W14-13): the person's own work, written down so it can
  be passed on when the server did not take it. One JSON file with the written work, and the photos
  and videos as they were taken. `buildExport` is plain data; `deliver` hands the files to the
  phone's share sheet where it exists and downloads them where it does not.
*/

export interface ExportSource {
  visit: { id: string, ref: string, title: string }
  station: { code: string, name: string } | null
  reason: { code: string, what: string, text: string }
  /** The element as the phone holds it. */
  element: unknown
  /** The server's copy, when the answer carried it. */
  server_copy: unknown
  operations: { type: string, created_at: string, payload: unknown }[]
  blobs: LocalBlob[]
  at: Date
}

export interface ExportFiles {
  json: File
  media: File[]
  /** What the sheet lists: written items, files, and the size of the files. */
  summary: { written: number, files: number, bytes: number }
}

const SAFE = /[^\w.-]+/g

function mediaName (blob: LocalBlob, taken: Set<string>): string {
  const base = (blob.name ?? `${blob.kind ?? 'file'}-${blob.media_id.slice(-8)}`).replaceAll(SAFE, '_')
  let name = base
  for (let n = 2; taken.has(name); n++) {
    name = `${n}-${base}`
  }
  taken.add(name)
  return name
}

export function buildExport (source: ExportSource): ExportFiles {
  const taken = new Set<string>()
  const media = source.blobs.map(blob => new File([blob.file], mediaName(blob, taken), { type: blob.file.type }))
  const record = {
    exported_by: 'MARS-MMS',
    exported_at: source.at.toISOString(),
    visit: source.visit,
    station: source.station,
    reason: source.reason,
    your_copy: source.element,
    server_copy: source.server_copy,
    operations: source.operations,
    files: source.blobs.map((blob, index) => ({
      name: media[index]!.name, kind: blob.kind ?? null, size: blob.size, sha256: blob.sha256,
    })),
  }
  const stamp = source.at.toISOString().slice(0, 10)
  const json = new File(
    [JSON.stringify(record, null, 2)],
    `${source.visit.ref}${source.station ? `-${source.station.code}` : ''}-${stamp}.json`.replaceAll(SAFE, '_'),
    { type: 'application/json' },
  )
  return {
    json,
    media,
    summary: {
      written: Math.max(source.operations.filter(op => op.type.startsWith('element.')).length, source.element ? 1 : 0)
        + source.operations.filter(op => op.type.startsWith('station.')).length,
      files: media.length,
      bytes: media.reduce((sum, file) => sum + file.size, 0),
    },
  }
}

export type Delivery = 'shared' | 'saved' | 'cancelled'

/** Share where the browser can share these files, else save them (Downloads). */
export async function deliver (files: ExportFiles, mode: 'share' | 'save'): Promise<Delivery> {
  const all = [files.json, ...files.media]
  if (mode === 'share' && typeof navigator.canShare === 'function' && navigator.canShare({ files: all })) {
    try {
      await navigator.share({ files: all, title: files.json.name })
      return 'shared'
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return 'cancelled'
      }
      // The sheet refused (a size limit, a missing permission): fall back to saving
    }
  }
  for (const file of all) {
    const url = URL.createObjectURL(file)
    const link = document.createElement('a')
    link.href = url
    link.download = file.name
    document.body.append(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 10_000)
  }
  return 'saved'
}
