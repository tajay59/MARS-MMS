import type { LocalFile } from '@/offline/db'

/*
  Shows a file kept on the phone (CFG-4, DOC-2). The blob becomes a temporary address in this tab's
  memory (`blob:` is allowed by the CSP for media and images); it is released a minute later. The
  phone's own viewer or share sheet takes over from there, which is why a PDF needs no viewer of
  ours (W13-13; the bundled one stays out of the precache, F17).
*/

const KEEP_MS = 60_000

export function openStoredFile (file: Pick<LocalFile, 'blob' | 'name' | 'content_type'>): void {
  const typed = file.blob.type ? file.blob : new Blob([file.blob], { type: file.content_type })
  const url = URL.createObjectURL(typed)
  const opened = globalThis.open(url, '_blank', 'noopener')
  if (!opened) {
    // A blocked pop-up (or an installed app with no tabs): save it instead
    const link = document.createElement('a')
    link.href = url
    link.download = file.name
    document.body.append(link)
    link.click()
    link.remove()
  }
  setTimeout(() => URL.revokeObjectURL(url), KEEP_MS)
}
