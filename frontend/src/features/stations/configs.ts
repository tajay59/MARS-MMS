import type { ConfigDiff, ConfigFileOut, ConfigVersionOut } from '@/api/models'

/*
  Configuration versions (PRD CFG-1 to CFG-3): the files of a station's logger and modem, saved as
  numbered sets that never change. No Vue here, so Vitest covers it directly.
*/

export type Change = 'changed' | 'added' | 'removed' | 'unchanged'

export interface FileRow {
  filename: string
  change: Change
  size_bytes: number
  sha256: string
  /** The file in the version shown; for a removed file, the one in the earlier version. */
  media_id: string
}

const order: Record<Change, number> = { changed: 0, added: 1, unchanged: 2, removed: 3 }

/** The rows of the diff table: the version's files with what changed, then those it dropped. */
export function fileRows (version: ConfigVersionOut, against: ConfigVersionOut | null, diff: ConfigDiff | null): FileRow[] {
  const changeOf = new Map<string, Change>()
  for (const name of diff?.changed ?? []) {
    changeOf.set(name, 'changed')
  }
  for (const name of diff?.added ?? []) {
    changeOf.set(name, 'added')
  }
  const rows: FileRow[] = version.files.map((f: ConfigFileOut) => ({
    filename: f.filename,
    change: changeOf.get(f.filename) ?? 'unchanged',
    size_bytes: f.size_bytes,
    sha256: f.sha256,
    media_id: f.media_id,
  }))
  const removed = new Set(diff?.removed)
  for (const f of against?.files ?? []) {
    if (removed.has(f.filename)) {
      rows.push({ filename: f.filename, change: 'removed', size_bytes: f.size_bytes, sha256: f.sha256, media_id: f.media_id })
    }
  }
  // Stable: files keep the order they were saved in within each group
  return rows
    .map((row, i) => ({ row, i }))
    .toSorted((a, b) => order[a.row.change] - order[b.row.change] || a.i - b.i)
    .map(x => x.row)
}

export function changeCounts (rows: readonly FileRow[]): Record<Change, number> {
  const counts: Record<Change, number> = { changed: 0, added: 0, removed: 0, unchanged: 0 }
  for (const row of rows) {
    counts[row.change]++
  }
  return counts
}

/** The first characters of a checksum are enough to tell two files apart on screen. */
export function shortHash (sha256: string): string {
  return sha256.slice(0, 8)
}

export const changeLook: Record<Change, { label: string, chip: string }> = {
  changed: { label: 'Changed', chip: 'bg-warning-container text-on-warning-container' },
  added: { label: 'Added', chip: 'bg-success-container text-on-success-container' },
  removed: { label: 'Removed', chip: 'bg-error-container text-on-error-container' },
  unchanged: { label: 'Unchanged', chip: 'bg-surface-100 text-surface-700' },
}

/** The number the next version will have. */
export function nextVersionNumber (versions: readonly Pick<ConfigVersionOut, 'version'>[]): number {
  return versions.reduce((max, v) => Math.max(max, v.version), 0) + 1
}

/** Two files in one version can't share a name, whatever the case (the server refuses it too). */
export function duplicateName (names: readonly string[], candidate: string): boolean {
  const key = candidate.toLowerCase()
  return names.some(n => n.toLowerCase() === key)
}
