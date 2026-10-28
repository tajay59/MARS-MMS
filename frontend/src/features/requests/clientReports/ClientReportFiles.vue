<template>
  <!-- A PDF report: one PDF -->
  <div v-if="kind === 'pdf'" class="flex flex-col gap-2.5">
    <span id="crf-pdf-l" class="text-label text-surface-900">The PDF</span>

    <div
      v-if="!files.pdf.value"
      aria-labelledby="crf-pdf-l"
      class="flex flex-wrap items-center gap-4 rounded-card border-2 border-dashed px-4 py-5"
      :class="dragging ? 'border-primary bg-primary-50' : 'border-surface-300 bg-surface-50'"
      @dragenter.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @dragover.prevent
      @drop.prevent="onDropPdf"
    >
      <v-icon class="shrink-0 text-primary" :icon="mdiTrayArrowUp" size="28" />

      <div class="min-w-0 grow basis-48">
        <div class="font-semibold text-surface-900">Choose a PDF or drop it here</div>
        <div class="text-sm text-surface-600">Up to 25 MB.</div>
      </div>

      <v-btn color="primary" variant="outlined" @click="pdfInput?.click()">Choose a PDF</v-btn>
    </div>

    <div
      v-else
      class="relative flex items-center gap-3 overflow-hidden rounded-xl px-3 py-2 shadow-[inset_0_0_0_1px_var(--v-theme-surface-200)]"
      :class="pdfFailed ? 'bg-error-container text-on-error-container' : ''"
    >
      <v-icon class="shrink-0" :class="pdfFailed ? '' : 'text-error'" :icon="pdfFailed ? mdiAlertOutline : mdiFilePdfBox" size="22" />

      <span class="flex min-w-0 grow flex-col">
        <span class="truncate font-mono text-xs font-medium" translate="no">{{ files.pdf.value.name }}</span>
        <span class="text-xs tabular-nums" :class="pdfFailed ? '' : 'text-surface-600'">{{ pdfText }}</span>
      </span>

      <span v-if="files.pdfReady.value" aria-hidden="true" class="shrink-0 text-success"><v-icon :icon="mdiCheck" size="20" /></span>
      <v-btn v-if="files.pdf.value.upload?.state === 'failed'" size="x-small" variant="text" @click="files.retryPdf()">Try again</v-btn>

      <v-btn
        :aria-label="`Remove ${files.pdf.value.name}`"
        icon
        size="32"
        variant="text"
        @click="files.removePdf()"
      ><v-icon :icon="mdiClose" size="18" /></v-btn>
    </div>

    <input
      ref="pdfInput"
      accept="application/pdf,.pdf"
      aria-label="Choose the PDF"
      class="sr-only"
      data-testid="client-report-pdf"
      tabindex="-1"
      type="file"
      @change="onPickPdf"
    >

    <p v-if="error" class="m-0 text-sm text-error" role="alert">{{ error }}</p>
  </div>

  <!-- An online form: up to ten pictures, printed at the end of the PDF -->
  <div v-else class="flex flex-col gap-2.5">
    <span id="crf-pic-l" class="text-label text-surface-900">Pictures</span>

    <ul aria-labelledby="crf-pic-l" class="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-2 p-0">
      <li v-for="picture in files.pictures" :key="picture.key" class="flex min-w-0 flex-col gap-1">
        <div class="relative aspect-4/3 max-w-full overflow-hidden rounded-md bg-surface-100" :class="picture.problem || picture.upload?.state === 'failed' ? 'outline-2 outline-error' : ''">
          <img v-if="picture.previewUrl" alt="" class="size-full object-cover" :src="picture.previewUrl">

          <v-progress-circular
            v-if="picture.upload && picture.upload.state !== 'ready' && picture.upload.state !== 'failed'"
            class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
            indeterminate
            size="22"
            width="3"
          />

          <v-btn
            :aria-label="`Remove ${picture.name}`"
            class="absolute right-1 top-1 bg-surface"
            icon
            size="24"
            variant="flat"
            @click="files.removePicture(picture)"
          ><v-icon :icon="mdiClose" size="14" /></v-btn>
        </div>

        <span class="truncate font-mono text-xs text-surface-700" translate="no">{{ picture.name }}</span>
        <span v-if="picture.problem" class="text-xs text-error">{{ picture.problem }}</span>

        <span v-else-if="picture.upload?.state === 'failed'" class="flex items-center gap-1 text-xs text-error">
          {{ picture.upload.error ?? 'It did not upload.' }}
          <v-btn size="x-small" variant="text" @click="files.retryPicture(picture)">Try again</v-btn>
        </span>
      </li>

      <li v-if="files.pictures.length < MAX_IMAGES">
        <button
          class="grid aspect-4/3 w-full place-items-center rounded-md border border-dashed border-surface-500 bg-surface-50 text-primary hover:bg-surface-100"
          type="button"
          @click="pictureInput?.click()"
        >
          <span class="flex flex-col items-center gap-1 text-sm font-medium"><v-icon :icon="mdiPlus" size="22" />Add pictures</span>
        </button>
      </li>
    </ul>

    <span class="text-xs text-surface-600">{{ files.pictures.length }} of {{ MAX_IMAGES }}. JPEG or PNG. They go at the end of the PDF.</span>

    <input
      ref="pictureInput"
      accept="image/jpeg,image/png"
      aria-label="Choose pictures"
      class="sr-only"
      data-testid="client-report-pictures"
      multiple
      tabindex="-1"
      type="file"
      @change="onPickPictures"
    >

    <p v-if="files.notice.value" class="m-0 text-sm text-error" role="alert">{{ files.notice.value }}</p>
    <p v-if="error" class="m-0 text-sm text-error" role="alert">{{ error }}</p>
  </div>
</template>

<script lang="ts" setup>
  import type { useClientReportFiles } from './useClientReportFiles'
  import type { ClientReportOut } from '@/api/models'
  import { mdiAlertOutline, mdiCheck, mdiClose, mdiFilePdfBox, mdiPlus, mdiTrayArrowUp } from '@mdi/js'
  import { computed, ref } from 'vue'
  import { chipText } from '../attachments'
  import { MAX_IMAGES } from './clientReport'

  // The files part of the client report page (W18 board 5): one PDF, or up to ten pictures.
  const props = defineProps<{
    kind: ClientReportOut['kind']
    files: ReturnType<typeof useClientReportFiles>
    /** A problem with the files the page found when the person tried to send. */
    error?: string | null
  }>()

  const dragging = ref(false)
  const pdfInput = ref<HTMLInputElement | null>(null)
  const pictureInput = ref<HTMLInputElement | null>(null)

  const pdfFailed = computed(() => !!props.files.pdf.value?.problem || props.files.pdf.value?.upload?.state === 'failed')
  const pdfText = computed(() => {
    const draft = props.files.pdf.value
    if (!draft) {
      return ''
    }
    if (draft.upload === null && draft.problem === null) {
      return 'Ready'
    }
    return chipText(draft as Parameters<typeof chipText>[0])
  })

  function onPickPdf (event: Event): void {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0]
    if (file) {
      props.files.choosePdf(file)
    }
    input.value = ''
  }

  function onDropPdf (event: DragEvent): void {
    dragging.value = false
    const file = event.dataTransfer?.files[0]
    if (file) {
      props.files.choosePdf(file)
    }
  }

  function onPickPictures (event: Event): void {
    const input = event.target as HTMLInputElement
    if (input.files) {
      void props.files.addPictures([...input.files])
    }
    input.value = ''
  }
</script>
