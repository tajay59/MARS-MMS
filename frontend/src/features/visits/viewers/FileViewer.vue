<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <div class="flex items-center gap-2 border-b border-surface-200 py-1.5 pl-1 pr-3">
      <v-btn class="text-primary" :prepend-icon="mdiArrowLeft" variant="text" @click="emit('back')">{{ backLabel }}</v-btn>
      <span class="min-w-0 flex-1 truncate text-right font-mono text-xs text-surface-600" translate="no">{{ file.filename }}</span>
    </div>

    <div v-if="state === 'loading'" aria-label="Opening the file…" class="flex flex-1 items-center justify-center p-8" role="status">
      <v-progress-circular color="primary" indeterminate size="28" />
    </div>

    <!-- Photos and video: on black, paging through the section's other photos and videos -->
    <template v-else-if="state === 'ready' && (kind === 'image' || kind === 'video')">
      <div class="relative flex min-h-[320px] flex-1 items-center justify-center bg-black">
        <img
          v-if="kind === 'image'"
          :alt="file.caption || `Photo ${position} of ${total}`"
          class="h-auto max-h-[60dvh] w-auto max-w-full object-contain"
          :height="detail?.height ?? undefined"
          :src="urls.view"
          :width="detail?.width ?? undefined"
        >

        <video
          v-else
          :aria-label="file.caption || `Video ${position} of ${total}`"
          class="max-h-[60dvh] max-w-full"
          controls
          playsinline
          :poster="urls.thumbnail"
          preload="metadata"
          :src="urls.view"
        />

        <span v-if="total > 1" class="absolute left-1/2 top-2.5 -translate-x-1/2 rounded-full bg-black/60 px-2.5 py-0.5 text-xs font-semibold tabular-nums text-white">{{ position }} of {{ total }}</span>

        <button
          v-if="total > 1"
          aria-label="Previous"
          class="absolute left-2.5 top-1/2 grid size-11 -translate-y-1/2 cursor-pointer place-items-center rounded-full border-0 bg-white/15 text-white hover:bg-white/25"
          type="button"
          @click="step(-1)"
        ><v-icon :icon="mdiChevronLeft" /></button>

        <button
          v-if="total > 1"
          aria-label="Next"
          class="absolute right-2.5 top-1/2 grid size-11 -translate-y-1/2 cursor-pointer place-items-center rounded-full border-0 bg-white/15 text-white hover:bg-white/25"
          type="button"
          @click="step(1)"
        ><v-icon :icon="mdiChevronRight" /></button>
      </div>

      <div class="px-4 pb-3 pt-2.5 text-sm">
        <p v-if="file.caption" class="m-0 text-surface-900">{{ file.caption }}</p>
        <p class="m-0 text-xs text-surface-600">{{ takenLine }}</p>
      </div>
    </template>

    <PdfViewer v-else-if="state === 'ready' && kind === 'pdf'" :url="urls.view!" />

    <TextViewer
      v-else-if="state === 'ready' && kind === 'text' && !unreadable"
      :filename="file.filename"
      :url="urls.view!"
      @unreadable="unreadable = $event"
    />

    <!-- Anything else, a file still being checked, or no signal -->
    <div v-else class="flex flex-1 flex-col items-center justify-center gap-2.5 px-6 py-10 text-center">
      <span class="grid size-16 place-items-center rounded-2xl text-sm font-bold" :class="offline ? 'bg-surface-100 text-surface-600' : 'bg-sticky-config text-on-sticky-config'">
        <v-icon v-if="offline" :icon="mdiWifiOff" size="28" />
        <template v-else>{{ badge(file.filename) }}</template>
      </span>

      <b class="text-base text-surface-900">{{ fallback.title }}</b>
      <p class="m-0 max-w-[34ch] text-sm text-surface-700">{{ fallback.text }}</p>

      <v-btn v-if="offline" variant="outlined" @click="look()">Try again</v-btn>
      <v-btn v-else-if="urls.download" color="primary" :href="urls.download" :prepend-icon="icons.download">Download</v-btn>
    </div>
  </div>
</template>

<script lang="ts" setup>
  import type { BoardMedia, MediaDetail } from '@/api/models'
  import { mdiArrowLeft, mdiChevronLeft, mdiChevronRight, mdiWifiOff } from '@mdi/js'
  import { computed, onBeforeUnmount, ref, watch } from 'vue'
  import { formatDateTime } from '@/app/format'
  import { icons } from '@/app/theme/icons'
  import { mediaDetail, onItsWay } from '../mediaLinks'
  import PdfViewer from './PdfViewer.vue'
  import TextViewer from './TextViewer.vue'
  import { badge, gallery, sizeText, viewKind } from './view'

  // A file shown inside the element sheet, never in a new tab (W11-29): a photo or video on black,
  // paging through the section's others; a PDF drawn by pdf.js; a text or code file as text; any
  // other file as its name, size and Download. Links last ten minutes and are asked for on open.
  const props = defineProps<{
    /** The file opened, and the files of its section (photos and video page through together). */
    file: BoardMedia
    files: readonly BoardMedia[]
    /** Where Back goes: the element's title. */
    backLabel: string
    zone?: string | null
  }>()

  const emit = defineEmits<{ 'back': [], 'update:file': [file: BoardMedia] }>()

  const detail = ref<MediaDetail | null>(null)
  const state = ref<'loading' | 'ready' | 'processing' | 'failed' | 'offline'>('loading')
  const unreadable = ref<'binary' | 'offline' | 'failed' | null>(null)

  const kind = computed(() => viewKind(props.file))
  const urls = computed(() => detail.value?.urls ?? {})
  const pages = computed(() => gallery(props.files))
  const total = computed(() => pages.value.length)
  const position = computed(() => pages.value.findIndex(f => f.media_id === props.file.media_id) + 1)
  const offline = computed(() => state.value === 'offline' || unreadable.value === 'offline')
  const takenLine = computed(() => {
    const at = formatDateTime(props.file.captured_at ?? props.file.added_at, props.zone)
    return `${props.file.captured_at ? 'Taken' : 'Added'} ${at} · ${props.file.added_by.name}`
  })

  const fallback = computed(() => {
    if (offline.value) {
      return { title: 'This needs a connection', text: 'PDFs and text files open when you have signal. Photos and video still show once they have loaded.' }
    }
    if (state.value === 'processing') {
      return { title: 'Still being checked', text: 'The file has arrived and is being checked. It opens here in a minute or two.' }
    }
    if (state.value === 'failed' || unreadable.value === 'failed') {
      return { title: 'We couldn’t open this file', text: 'Try again in a moment, or download it.' }
    }
    const size = sizeText(props.file.size_bytes)
    return { title: props.file.filename, text: `${size ? `${size}. ` : ''}This kind of file can’t be shown here. Download it to open it on your computer.` }
  })

  function step (by: -1 | 1): void {
    const list = pages.value
    const at = list.findIndex(f => f.media_id === props.file.media_id)
    const next = list[(at + by + list.length) % list.length]
    if (next) {
      emit('update:file', next)
    }
  }

  let timer: ReturnType<typeof setTimeout> | undefined
  let gone = false

  /** Ask media about the file; while it is still being checked, ask again every few seconds. */
  async function look (quiet = false): Promise<void> {
    clearTimeout(timer)
    if (!quiet) {
      state.value = 'loading'
      unreadable.value = null
    }
    const id = props.file.media_id
    try {
      const found = await mediaDetail(id)
      if (gone || id !== props.file.media_id) {
        return
      }
      detail.value = found
      if (found.status === 'ready') {
        state.value = 'ready'
      } else if (onItsWay(found.status)) {
        state.value = 'processing'
        timer = setTimeout(() => void look(true), 5000)
      } else {
        state.value = 'failed'
      }
    } catch {
      state.value = navigator.onLine ? 'failed' : 'offline'
    }
  }

  watch(() => props.file.media_id, () => void look(), { immediate: true })
  onBeforeUnmount(() => {
    gone = true
    clearTimeout(timer)
  })
</script>
