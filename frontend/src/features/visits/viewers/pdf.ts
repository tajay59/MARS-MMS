import type * as PdfJsModule from 'pdfjs-dist'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import PdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?worker'

/*
  pdf.js for the PDF viewer (W11-29, W11-30, finding F17). The library is loaded with import(), so
  it stays out of the app chunk and the first install; it and its worker are left out of the
  precache (vite.config.mts), so a PDF needs a connection until Phase 5. The worker is a bundled
  file from our own origin, because the CSP's worker-src 'self' refuses blob: workers; pdf.js 6
  uses no eval, and its WebAssembly decoders are off because the CSP allows no wasm. The whole file
  is fetched once (no range requests), which needs no CORS headers beyond the files host's allowed
  origin.
*/

type PdfJs = typeof PdfJsModule

let loading: Promise<PdfJs> | null = null

export function loadPdfJs (): Promise<PdfJs> {
  loading ??= import('pdfjs-dist').then(pdfjs => {
    pdfjs.GlobalWorkerOptions.workerPort = new PdfWorker()
    return pdfjs
  }).catch(error => {
    loading = null // a failed chunk load (offline) can be tried again
    throw error
  })
  return loading
}

export interface OpenedPdf {
  doc: PDFDocumentProxy
  /** Free the worker's copy of the document. */
  close: () => Promise<void>
}

export async function openPdf (url: string): Promise<OpenedPdf> {
  const pdfjs = await loadPdfJs()
  const task = pdfjs.getDocument({
    url,
    useWasm: false,
    disableRange: true,
    disableStream: true,
    disableAutoFetch: true,
  })
  return { doc: await task.promise, close: () => task.destroy() }
}
