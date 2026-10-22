import type { BoardMedia } from '@/api/models'

/*
  Which viewer shows a file inside the element sheet (W11-29): never a new tab. Photos and video
  play from the media service's processed copy; a PDF is drawn by pdf.js; a text or code file is
  read as UTF-8 and shown as text, never as HTML; anything else gets its name, size and Download.
  No Vue here.
*/

export type ViewKind = 'image' | 'video' | 'pdf' | 'text' | 'file'

/** Text files are shown up to this size; a larger one is downloaded. */
export const TEXT_LIMIT = 1024 * 1024

// Logger programs (Campbell CRBasic .CR1, .CR6, .CR300 …), modem settings and the usual text files
const TEXT_EXTENSIONS = new Set([
  'txt', 'py', 'ttx', 'csv', 'tsv', 'json', 'xml', 'ini', 'cfg', 'conf', 'log', 'md', 'yaml', 'yml',
  'toml', 'sql', 'dat', 'cr1', 'cr1x', 'cr2', 'cr3', 'cr5', 'cr6', 'cr8', 'cr9', 'cr300', 'cr350',
  'cr800', 'cr850', 'cr1000', 'crb', 'dld', 'prg', 'bas',
])

export function extension (filename: string): string {
  const name = filename.toLowerCase()
  const dot = name.lastIndexOf('.')
  return dot <= 0 || dot === name.length - 1 ? '' : name.slice(dot + 1)
}

/** The badge on a file row: "PDF", "PY", "CR1"; "FILE" when there is no extension. */
export function badge (filename: string): string {
  const ext = extension(filename)
  return ext ? ext.slice(0, 4).toUpperCase() : 'FILE'
}

export function viewKind (file: Pick<BoardMedia, 'kind' | 'filename' | 'size_bytes'>): ViewKind {
  if (file.kind === 'image' || file.kind === 'video') {
    return file.kind
  }
  const ext = extension(file.filename)
  if (ext === 'pdf') {
    return 'pdf'
  }
  if (TEXT_EXTENSIONS.has(ext) && (file.size_bytes ?? 0) <= TEXT_LIMIT) {
    return 'text'
  }
  return 'file'
}

/** UTF-8 text with no NUL byte, or null: a file that only looks like text is shown as a file. */
export function decodeText (bytes: ArrayBuffer): string | null {
  const view = new Uint8Array(bytes)
  if (view.includes(0)) {
    return null
  }
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(view)
  } catch {
    return null
  }
}

/** The text's lines, without a last empty one after a final newline. */
export function linesOf (text: string): string[] {
  const lines = text.replaceAll('\r\n', '\n').split('\n')
  if (lines.length > 1 && lines.at(-1) === '') {
    lines.pop()
  }
  return lines
}

/** "18 KB", "1.2 MB": a size for people. */
export function sizeText (bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || bytes < 0) {
    return ''
  }
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** The files of a section that page through together in the viewer: photos and video. */
export function gallery (files: readonly BoardMedia[]): BoardMedia[] {
  return files.filter(f => f.kind === 'image' || f.kind === 'video')
}
