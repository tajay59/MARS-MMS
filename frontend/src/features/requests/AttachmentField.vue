<template>
  <div class="flex flex-col gap-2.5">
    <!-- The form: a drop zone. The composer: a small button. -->
    <div
      v-if="!compact"
      class="flex flex-wrap items-center gap-4 rounded-card border-2 border-dashed px-4 py-5"
      :class="dragging ? 'border-primary bg-primary-50' : 'border-surface-300 bg-surface-50'"
      @dragenter.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @dragover.prevent
      @drop.prevent="onDrop"
    >
      <v-icon class="shrink-0 text-primary" :icon="icons.upload" size="28" />

      <div class="min-w-0 grow basis-48">
        <div class="font-semibold text-surface-900">Drop PDF files here</div>
        <div class="text-sm text-surface-600">or choose them from this device. Photos can be added to the visit later.</div>
      </div>

      <v-btn color="primary" :disabled="drafts.full.value" variant="outlined" @click="picker?.click()">Choose files</v-btn>
    </div>

    <v-btn
      v-else
      class="self-start"
      color="primary"
      :disabled="drafts.full.value"
      :prepend-icon="mdiPaperclip"
      size="small"
      variant="outlined"
      @click="picker?.click()"
    >Attach PDF</v-btn>

    <input
      ref="picker"
      accept="application/pdf,.pdf"
      aria-label="Choose PDF files to attach"
      class="sr-only"
      data-testid="attachment-file"
      multiple
      tabindex="-1"
      type="file"
      @change="onPick"
    >

    <p v-if="drafts.notice.value" class="m-0 text-sm text-error" role="alert">{{ drafts.notice.value }}</p>

    <ul v-if="drafts.drafts.length > 0" aria-label="Files to attach" class="m-0 flex list-none flex-col gap-1.5 p-0">
      <li
        v-for="draft in drafts.drafts"
        :key="draft.key"
        class="relative flex items-center gap-3 overflow-hidden rounded-xl px-3 py-2 shadow-[inset_0_0_0_1px_var(--v-theme-surface-200)]"
        :class="draft.problem || draft.upload?.state === 'failed' ? 'bg-error-container text-on-error-container' : ''"
      >
        <v-icon class="shrink-0" :class="draft.problem || draft.upload?.state === 'failed' ? '' : 'text-error'" :icon="draft.problem || draft.upload?.state === 'failed' ? mdiAlertOutline : mdiFilePdfBox" size="22" />

        <span class="flex min-w-0 grow flex-col">
          <span class="truncate font-mono text-xs font-medium" translate="no">{{ draft.name }}</span>
          <span class="text-xs tabular-nums" :class="draft.problem || draft.upload?.state === 'failed' ? '' : 'text-surface-600'">{{ chipText(draft) }}</span>
        </span>

        <span v-if="draft.upload?.state === 'ready'" aria-hidden="true" class="shrink-0 text-success"><v-icon :icon="mdiCheck" size="20" /></span>
        <v-btn v-if="draft.upload?.state === 'failed'" size="x-small" variant="text" @click="drafts.retry(draft)">Try again</v-btn>

        <v-btn
          :aria-label="`Remove ${draft.name}`"
          icon
          size="32"
          variant="text"
          @click="drafts.remove(draft)"
        >
          <v-icon :icon="mdiClose" size="18" />
        </v-btn>

        <span
          v-if="draft.upload && draft.upload.state !== 'ready' && draft.upload.state !== 'failed'"
          aria-label="Upload progress"
          aria-valuemax="100"
          aria-valuemin="0"
          :aria-valuenow="percent(draft.upload.sent, draft.upload.total)"
          class="absolute inset-x-3 bottom-0.5 h-0.5 rounded-full bg-surface-200"
          role="progressbar"
        >
          <span class="block h-full rounded-full bg-primary" :style="{ width: `${percent(draft.upload.sent, draft.upload.total)}%` }" />
        </span>
      </li>
    </ul>
  </div>
</template>

<script lang="ts" setup>
  import type { AttachmentDrafts } from './useAttachmentDrafts'
  import { mdiAlertOutline, mdiCheck, mdiClose, mdiFilePdfBox, mdiPaperclip } from '@mdi/js'
  import { ref } from 'vue'
  import { icons } from '@/app/theme/icons'
  import { percent } from '@/features/stations/documents'
  import { chipText } from './attachments'

  // Choose, drop and watch PDFs go up (PRD REQ-3). The files are the parent's `drafts`: it knows
  // what they will belong to and when they are all ready.
  const props = defineProps<{
    drafts: AttachmentDrafts
    /** A button, not a drop zone: for the comment composer. */
    compact?: boolean
  }>()

  const picker = ref<HTMLInputElement | null>(null)
  const dragging = ref(false)

  function onPick (event: Event): void {
    const input = event.target as HTMLInputElement
    props.drafts.add(input.files ?? [])
    input.value = ''
  }

  function onDrop (event: DragEvent): void {
    dragging.value = false
    props.drafts.add(event.dataTransfer?.files ?? [])
  }
</script>
