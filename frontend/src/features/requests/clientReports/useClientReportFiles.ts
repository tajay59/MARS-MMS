import type { ClientReportOut } from '@/api/models'
import type { Upload } from '@/app/composables/useUpload'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { clientReportsApi } from '@/api/operations'
import { useUploads } from '@/app/composables/useUpload'
import { newId } from '@/app/ids'
import { prepareImage } from '@/offline/image'
import { pdfProblem } from '../attachments'
import { imageProblem, MAX_IMAGES } from './clientReport'

/*
  The files of a client report that is not sent yet (PRD CRP-1, CRP-2; W18-9, W18-10): one PDF for a
  PDF report, up to ten pictures for a form. Each goes up as soon as it is chosen, for the report's
  own owner reference, and is checked by media; the draft takes a file only once it is ready, so
  nothing unchecked is ever attached. Pictures are shrunk in the browser first, as visit photos are.
  Online only (OFF-10): nothing is stored on the device, and the previews are object URLs that are
  freed when the page goes.
*/

export interface PictureDraft {
  key: string
  name: string
  problem: string | null
  /** A checked file the draft already holds. */
  mediaId: string | null
  upload: Upload | null
  previewUrl: string | null
}

export interface PdfDraft {
  name: string
  size: number
  problem: string | null
  mediaId: string | null
  upload: Upload | null
}

export function useClientReportFiles (
  report: () => ClientReportOut | null,
  save: { setPdf: (id: string | null) => Promise<boolean>, setImages: (ids: string[]) => Promise<boolean> },
) {
  const uploads = useUploads()
  const pdf = ref<PdfDraft | null>(null)
  const pictures = reactive<PictureDraft[]>([])
  const notice = ref<string | null>(null)
  const urls: string[] = []

  const owner = () => `client_report:${report()?.id}`

  /** Pick up what the server already holds (Continue draft). */
  async function hold (doc: ClientReportOut): Promise<void> {
    if (doc.file) {
      pdf.value = { name: doc.file.name, size: doc.file.size_bytes, problem: null, mediaId: doc.file.media_id, upload: null }
    }
    const held = doc.form.images.map<PictureDraft>(image => ({
      key: image.media_id, name: image.name, problem: null, mediaId: image.media_id, upload: null, previewUrl: null,
    }))
    pictures.splice(0, pictures.length, ...held)
    await Promise.all(held.map(async picture => {
      try {
        picture.previewUrl = (await clientReportsApi.file(doc.id, picture.mediaId as string)).url
      } catch {
        picture.previewUrl = null
      }
    }))
  }

  // --- the PDF ---

  function choosePdf (file: File): void {
    notice.value = null
    const problem = pdfProblem(file)
    const draft: PdfDraft = { name: file.name, size: file.size, problem, mediaId: null, upload: null }
    if (!problem) {
      draft.upload = uploads.add(file, { ownerRef: owner(), kind: 'pdf', untilChecked: true })
    }
    pdf.value = draft
    if (draft.upload) {
      void draft.upload.start()
    }
  }

  async function removePdf (): Promise<void> {
    const draft = pdf.value
    pdf.value = null
    if (draft?.upload) {
      await draft.upload.cancel()
      uploads.drop(draft.upload)
    }
    if (draft?.mediaId || draft?.upload?.mediaId) {
      await save.setPdf(null)
    }
  }

  function retryPdf (): void {
    if (pdf.value?.upload?.state === 'failed') {
      pdf.value.upload.reset()
      void pdf.value.upload.start()
    }
  }

  // The draft takes the PDF once media has checked it
  watch(() => pdf.value?.upload?.state, state => {
    const draft = pdf.value
    if (state === 'ready' && draft?.upload?.mediaId && draft.mediaId !== draft.upload.mediaId) {
      draft.mediaId = draft.upload.mediaId
      void save.setPdf(draft.mediaId)
    }
  })

  // --- the pictures ---

  async function addPictures (files: Iterable<File>): Promise<void> {
    notice.value = null
    for (const file of files) {
      if (pictures.length >= MAX_IMAGES) {
        notice.value = `Up to ${MAX_IMAGES} pictures can be added.`
        break
      }
      const problem = imageProblem(file)
      const picture: PictureDraft = { key: newId(), name: file.name, problem, mediaId: null, upload: null, previewUrl: null }
      pictures.push(picture)
      if (problem) {
        continue
      }
      const prepared = await prepareImage(file)
      picture.previewUrl = URL.createObjectURL(prepared.file)
      urls.push(picture.previewUrl)
      // The picture may have been removed while it was being prepared
      if (pictures.includes(picture)) {
        picture.upload = uploads.add(prepared.file, { ownerRef: owner(), kind: 'image', untilChecked: true })
        void picture.upload.start()
      }
    }
  }

  async function removePicture (picture: PictureDraft): Promise<void> {
    const at = pictures.indexOf(picture)
    if (at !== -1) {
      pictures.splice(at, 1)
    }
    if (picture.upload) {
      await picture.upload.cancel()
      uploads.drop(picture.upload)
    }
    if (picture.mediaId) {
      await save.setImages(readyIds())
    }
  }

  function retryPicture (picture: PictureDraft): void {
    if (picture.upload?.state === 'failed') {
      picture.upload.reset()
      void picture.upload.start()
    }
  }

  function readyIds (): string[] {
    return pictures.flatMap(p => {
      if (p.mediaId) {
        return [p.mediaId]
      }
      return p.upload?.state === 'ready' && p.upload.mediaId ? [p.upload.mediaId] : []
    })
  }

  // A picture joins the draft once it is ready, in the order it was added
  watch(() => pictures.map(p => `${p.key}:${p.upload?.state ?? ''}`).join('|'), () => {
    let changed = false
    for (const p of pictures) {
      if (!p.mediaId && p.upload?.state === 'ready' && p.upload.mediaId) {
        p.mediaId = p.upload.mediaId
        changed = true
      }
    }
    if (changed) {
      void save.setImages(readyIds())
    }
  })

  const busy = computed(() => {
    const files = [pdf.value, ...pictures]
    return files.some(f => f !== null && f.problem === null && f.upload !== null && f.upload.state !== 'ready')
  })
  const pdfReady = computed(() => !!pdf.value?.mediaId && pdf.value.problem === null)

  onBeforeUnmount(() => {
    for (const url of urls) {
      URL.revokeObjectURL(url)
    }
  })

  return { pdf, pictures, notice, busy, pdfReady, hold, choosePdf, removePdf, retryPdf, addPictures, removePicture, retryPicture }
}
