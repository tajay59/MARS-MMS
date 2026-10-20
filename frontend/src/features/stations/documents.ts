import type { DocumentOut } from '@/api/models'
import { mdiFileCodeOutline, mdiFileDelimitedOutline, mdiFileExcelOutline, mdiFileImageOutline, mdiFileOutline, mdiFilePdfBox, mdiFilePowerpointOutline, mdiFileWordOutline } from '@mdi/js'

/*
  Documents and configuration files on the station page (PRD DOC-1 to DOC-4, CFG-1 to CFG-3).
  No Vue here, so Vitest covers it directly. The server owns the rules; these checks only save a
  round trip and word the answer.
*/

export const MiB = 1024 * 1024
/** MED-6: 50 MB for a document or a configuration file. */
export const MAX_FILE_BYTES = 50 * MiB

export type DocScope = 'station' | 'model'

export const docTypes: Record<DocScope, { value: string, label: string }[]> = {
  station: [
    { value: 'installation', label: 'Installation' },
    { value: 'site_drawing', label: 'Site drawing' },
    { value: 'other', label: 'Other' },
  ],
  model: [
    { value: 'datasheet', label: 'Datasheet' },
    { value: 'operations_manual', label: 'Operations manual' },
    { value: 'maintenance_manual', label: 'Maintenance manual' },
    { value: 'other', label: 'Other' },
  ],
}

export const languages = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'nl', label: 'Dutch' },
  { value: 'pt', label: 'Portuguese' },
]

/** A sensor model's photo: a document the gallery shows rather than the document list (W6-12). */
export const PHOTO_TYPE = 'photo'

export function docTypeLabel (docType: string): string {
  if (docType === PHOTO_TYPE) {
    return 'Photo'
  }
  for (const list of Object.values(docTypes)) {
    const found = list.find(t => t.value === docType)
    if (found) {
      return found.label
    }
  }
  return docType
}

export function languageLabel (code: string | null | undefined): string {
  return languages.find(l => l.value === code)?.label ?? code ?? '—'
}

/** The extensions media accepts for a document (media/app/domain/media.py DOCUMENT_TYPES). */
export const DOCUMENT_EXTENSIONS = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.txt', '.csv', '.png', '.jpg', '.jpeg']
/** The `accept` list for the file picker. */
export const DOCUMENT_ACCEPT = DOCUMENT_EXTENSIONS.join(',')
/** A photo is a picture the browser can show; media checks the bytes match the name. */
export const IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg']
export const IMAGE_ACCEPT = IMAGE_EXTENSIONS.join(',')

/** Configuration sets take any extension except the ones an operating system will run. */
export const BLOCKED_EXTENSIONS = ['.exe', '.dll', '.msi', '.bat', '.cmd', '.com', '.scr', '.ps1', '.vbs', '.js', '.mjs', '.jar', '.app', '.apk', '.html', '.htm', '.svg', '.hta', '.lnk', '.reg', '.sh']

export function extensionOf (filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot <= 0 ? '' : filename.slice(dot).toLowerCase()
}

/** Media's kind for a document file: a PDF is `pdf`, anything else it accepts is `document`. */
export function documentKind (filename: string): 'pdf' | 'document' {
  return extensionOf(filename) === '.pdf' ? 'pdf' : 'document'
}

/** Why this file can't go up as it is, in words for the person; null when it can. */
export function fileProblem (file: { name: string, size: number }, purpose: 'document' | 'config' | 'photo'): string | null {
  const ext = extensionOf(file.name)
  if (file.size === 0) {
    return 'This file is empty.'
  }
  if (file.size > MAX_FILE_BYTES) {
    return `This file is ${formatBytes(file.size)}. The most that can be uploaded here is 50 MB.`
  }
  if (purpose === 'document' && !DOCUMENT_EXTENSIONS.includes(ext)) {
    return `${ext || 'This kind of'} files can’t be uploaded here. Use PDF, Word, Excel, PowerPoint, an image or text.`
  }
  if (purpose === 'photo' && !IMAGE_EXTENSIONS.includes(ext)) {
    return 'A photo has to be a PNG or JPEG picture.'
  }
  if (purpose === 'config' && BLOCKED_EXTENSIONS.includes(ext)) {
    return `${ext} files can’t be uploaded here.`
  }
  return null
}

/** `48 KB`, `1.8 MB`, `2.4 MB`: decimal-looking sizes people expect from a file list. */
export function formatBytes (bytes: number): string {
  if (bytes < 1000) {
    return `${bytes} B`
  }
  const kb = bytes / 1024
  if (kb < 1000) {
    return `${kb < 10 ? kb.toFixed(1) : Math.round(kb)} KB`
  }
  const mb = bytes / MiB
  return `${mb < 100 ? mb.toFixed(1) : Math.round(mb)} MB`
}

/** The title to offer from a file name: `kin-power-wiring.pdf` → `kin power wiring`. */
export function titleFromFilename (filename: string): string {
  const ext = extensionOf(filename)
  const base = ext ? filename.slice(0, -ext.length) : filename
  return base.replaceAll(/[_-]+/g, ' ').replaceAll(/\s+/g, ' ').trim()
}

/** Whether a document can be downloaded yet (the server refuses it otherwise). */
export function isDownloadable (doc: Pick<DocumentOut, 'status'>): boolean {
  return doc.status === 'available'
}

export type DocState = 'ready' | 'checking' | 'failed'

export function docState (doc: Pick<DocumentOut, 'status'>): DocState {
  if (doc.status === 'available') {
    return 'ready'
  }
  return doc.status === 'failed' ? 'failed' : 'checking'
}

/** What the virus scan or checks found, for a failed file. */
const failReasons: Record<string, string> = {
  infected: 'The virus scan found a problem with this file.',
  checksum_mismatch: 'The file changed on the way up.',
  bad_type: 'This kind of file isn’t allowed.',
  size_mismatch: 'The file arrived with the wrong size.',
}

export function failReason (reason: string | null | undefined): string {
  return (reason && failReasons[reason]) || 'The file did not pass its checks. Upload it again.'
}

/** How the upload dialog words what media answered when it refused a file. */
export function uploadFailure (reason: string | undefined, fallback: string): string {
  return (reason && failReasons[reason]) || fallback
}

/** Keeps the newest version of each document first, then by title. The server lists newest first. */
export function sortDocuments (docs: readonly DocumentOut[]): DocumentOut[] {
  return [...docs].toSorted((a, b) => b.created_at.localeCompare(a.created_at))
}

/** The version label (`v2`, `Rev C`), or a dash: `DocumentOut.version` counts edits to the record,
    not versions of the document, so it is never shown. */
export function versionText (doc: Pick<DocumentOut, 'version_label'>): string {
  return doc.version_label?.trim() || '—'
}

/** Progress as a whole percent, never 100 until the server holds the file. */
export function percent (sent: number, total: number, done = false): number {
  if (done) {
    return 100
  }
  return total <= 0 ? 0 : Math.min(99, Math.floor((sent / total) * 100))
}

/** An icon by file type; PDFs get the red mark the screens use for them. */
export function fileIcon (filename: string): { icon: string, tone: string } {
  switch (extensionOf(filename)) {
    case '.pdf': {
      return { icon: mdiFilePdfBox, tone: 'text-error' }
    }
    case '.doc':
    case '.docx':
    case '.odt': {
      return { icon: mdiFileWordOutline, tone: 'text-surface-600' }
    }
    case '.xls':
    case '.xlsx':
    case '.ods': {
      return { icon: mdiFileExcelOutline, tone: 'text-surface-600' }
    }
    case '.ppt':
    case '.pptx': {
      return { icon: mdiFilePowerpointOutline, tone: 'text-surface-600' }
    }
    case '.csv': {
      return { icon: mdiFileDelimitedOutline, tone: 'text-surface-600' }
    }
    case '.png':
    case '.jpg':
    case '.jpeg': {
      return { icon: mdiFileImageOutline, tone: 'text-surface-600' }
    }
    case '.xml':
    case '.json':
    case '.cfg':
    case '.cr1x': {
      return { icon: mdiFileCodeOutline, tone: 'text-surface-600' }
    }
    default: {
      return { icon: mdiFileOutline, tone: 'text-surface-600' }
    }
  }
}

/** Files the browser can show in place (media serves the rest as downloads). */
const INLINE_EXTENSIONS = new Set(['.pdf', '.png', '.jpg', '.jpeg'])

/**
 * Give the person a file from a ten-minute link, asked for on click and used at once: it is never
 * kept (TRD §7.6). A file the browser can show opens in a new tab, which is opened in the click
 * itself because Safari refuses a window opened after an `await`; a blocked one, and every file
 * that downloads, uses this tab (a download does not leave the page).
 */
export async function openDownload (filename: string, getLink: (inline: boolean) => Promise<{ url: string }>): Promise<void> {
  const inline = INLINE_EXTENSIONS.has(extensionOf(filename))
  const tab = inline ? globalThis.open('', '_blank') : null
  try {
    const { url } = await getLink(inline)
    if (tab) {
      tab.opener = null
      tab.location.href = url
    } else {
      globalThis.location.assign(url)
    }
  } catch (error) {
    tab?.close()
    throw error
  }
}
