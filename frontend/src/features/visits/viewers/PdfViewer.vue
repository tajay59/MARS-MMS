<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <div class="flex items-center gap-2 border-b border-surface-200 px-3 py-1.5 text-sm text-surface-700">
      <span aria-live="polite">{{ pages > 0 ? `${pages} ${pages === 1 ? 'page' : 'pages'}` : 'Opening…' }}</span>
      <span class="flex-1" />

      <v-btn
        aria-label="Zoom out"
        :disabled="zoom <= 0.5"
        icon
        size="small"
        variant="text"
        @click="setZoom(-0.25)"
      ><v-icon :icon="mdiMinus" /></v-btn>

      <span class="w-12 text-center tabular-nums">{{ Math.round(zoom * 100) }}%</span>

      <v-btn
        aria-label="Zoom in"
        :disabled="zoom >= 3"
        icon
        size="small"
        variant="text"
        @click="setZoom(0.25)"
      ><v-icon :icon="mdiPlus" /></v-btn>
    </div>

    <div
      ref="scroller"
      aria-label="Pages"
      class="min-h-0 flex-1 overflow-auto bg-surface-100 p-3"
      role="region"
      tabindex="0"
    >
      <div v-if="problem" class="py-8 text-center text-sm text-surface-700" role="alert">{{ problem }}</div>

      <div v-else class="mx-auto flex flex-col items-center gap-3" :style="{ width: `${zoom * 100}%` }">
        <canvas
          v-for="n in pages"
          :key="n"
          :ref="el => setCanvas(n, el)"
          :aria-label="`Page ${n} of ${pages}`"
          class="w-full bg-white shadow-sm"
          role="img"
        />
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
  import type { OpenedPdf } from './pdf'
  import type { PDFDocumentProxy } from 'pdfjs-dist'
  import { mdiMinus, mdiPlus } from '@mdi/js'
  import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
  import { openPdf } from './pdf'

  // A PDF drawn page by page in the element sheet (W11-29). Pages are drawn when they come into
  // view, at the width the sheet gives them, so a long manual does not draw every page at once.
  const props = defineProps<{ url: string }>()

  const scroller = ref<HTMLElement | null>(null)
  const pages = ref(0)
  const zoom = ref(1)
  const problem = ref<string | null>(null)
  const canvases = new Map<number, HTMLCanvasElement>()
  const drawn = new Set<number>()
  let doc: PDFDocumentProxy | null = null
  let opened: OpenedPdf | null = null
  let observer: IntersectionObserver | null = null
  let gone = false

  function setCanvas (n: number, el: unknown): void {
    if (el instanceof HTMLCanvasElement) {
      canvases.set(n, el)
      observer?.observe(el)
    }
  }

  async function draw (n: number): Promise<void> {
    const canvas = canvases.get(n)
    if (!doc || !canvas || drawn.has(n)) {
      return
    }
    drawn.add(n)
    const page = await doc.getPage(n)
    const width = canvas.clientWidth || 600
    const base = page.getViewport({ scale: 1 })
    const scale = (width / base.width) * Math.min(globalThis.devicePixelRatio || 1, 2)
    const viewport = page.getViewport({ scale })
    canvas.width = Math.floor(viewport.width)
    canvas.height = Math.floor(viewport.height)
    await page.render({ canvas, viewport }).promise
  }

  function redrawAll (): void {
    drawn.clear()
    for (const canvas of canvases.values()) {
      observer?.unobserve(canvas)
      observer?.observe(canvas)
    }
  }

  async function setZoom (by: number): Promise<void> {
    zoom.value = Math.min(3, Math.max(0.5, zoom.value + by))
    await nextTick()
    redrawAll()
  }

  async function open (): Promise<void> {
    problem.value = null
    pages.value = 0
    drawn.clear()
    canvases.clear()
    try {
      const next = await openPdf(props.url)
      if (gone) {
        await next.close()
        return
      }
      void opened?.close()
      opened = next
      doc = next.doc
      observer = new IntersectionObserver(entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const n = [...canvases].find(([, c]) => c === entry.target)?.[0]
            if (n !== undefined) {
              void draw(n)
            }
          }
        }
      }, { root: scroller.value, rootMargin: '400px 0px' })
      pages.value = next.doc.numPages
    } catch {
      problem.value = navigator.onLine
        ? 'We couldn’t open this PDF. Download it instead.'
        : 'This needs a connection. PDFs open when you have signal.'
    }
  }

  watch(() => props.url, open, { immediate: true })

  onBeforeUnmount(() => {
    gone = true
    observer?.disconnect()
    void opened?.close()
  })
</script>
