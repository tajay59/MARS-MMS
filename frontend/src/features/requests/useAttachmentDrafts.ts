import type { Upload } from '@/app/composables/useUpload'
import { computed, reactive, ref } from 'vue'
import { useUploads } from '@/app/composables/useUpload'
import { newId } from '@/app/ids'
import { allReady, MAX_FILES, pdfProblem } from './attachments'

/*
  The PDFs a person is attaching to a request or comment that is not sent yet. Each goes up as
  soon as it is chosen, under the owner reference of the thing it will belong to, and is checked
  by media; the form waits for all of them (W9-8). Online only (OFF-10): nothing is stored here.
*/

export interface Draft {
  key: string
  file: File
  size: number
  name: string
  problem: string | null
  upload: Upload | null
}

export function useAttachmentDrafts (ownerRef: () => string) {
  const uploads = useUploads()
  const drafts = reactive<Draft[]>([])
  const notice = ref<string | null>(null)

  const ready = computed(() => allReady(drafts))
  const readyIds = computed(() => drafts.flatMap(d => d.upload?.mediaId && d.upload.state === 'ready' ? [d.upload.mediaId] : []))
  const full = computed(() => drafts.length >= MAX_FILES)

  function add (files: Iterable<File>): void {
    notice.value = null
    for (const file of files) {
      if (drafts.length >= MAX_FILES) {
        notice.value = `Up to ${MAX_FILES} files can be attached.`
        break
      }
      const problem = pdfProblem(file)
      const draft: Draft = {
        key: newId(), file, size: file.size, name: file.name, problem, upload: null,
      }
      if (!problem) {
        draft.upload = uploads.add(file, { ownerRef: ownerRef(), kind: 'pdf', untilChecked: true })
      }
      drafts.push(draft)
      if (draft.upload) {
        void draft.upload.start()
      }
    }
  }

  async function remove (draft: Draft): Promise<void> {
    const at = drafts.indexOf(draft)
    if (at !== -1) {
      drafts.splice(at, 1)
    }
    if (draft.upload) {
      await draft.upload.cancel()
      uploads.drop(draft.upload)
    }
  }

  function retry (draft: Draft): void {
    if (draft.upload?.state === 'failed') {
      draft.upload.reset()
      void draft.upload.start()
    }
  }

  /** The files are now part of what was sent: forget them without touching the server. */
  function clear (): void {
    for (const draft of drafts.splice(0)) {
      if (draft.upload) {
        uploads.drop(draft.upload)
      }
    }
    notice.value = null
  }

  return { drafts, notice, ready, readyIds, full, add, remove, retry, clear }
}

export type AttachmentDrafts = ReturnType<typeof useAttachmentDrafts>
