<template>
  <ModalSheet
    labelledby="ud-h"
    :max-width="480"
    :model-value="open"
    persistent
    @update:model-value="onToggle"
  >
    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <div>
        <h2 id="ud-h" class="m-0 text-h2 text-surface-900">{{ heading }}</h2>

        <p class="m-0 mt-0.5 text-sm text-surface-600">
          {{ subject }}<template v-if="code"> · <span class="font-mono" translate="no">{{ code }}</span></template>
        </p>
      </div>

      <FeedbackBanner v-if="error" type="error">{{ error }}</FeedbackBanner>

      <!-- 1. Choose the file -->
      <div v-if="!locked && !upload">
        <div
          class="flex flex-col items-center gap-1.5 rounded-card border-[1.5px] border-dashed px-4 py-5 text-center"
          :class="dragging ? 'border-primary bg-primary-50' : 'border-surface-500 bg-surface-50'"
          @dragenter.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @dragover.prevent
          @drop.prevent="onDrop"
        >
          <v-icon class="text-surface-600" :icon="icons.upload" size="28" />
          <div class="text-label text-surface-900">Choose a file, or drop it here</div>
          <div class="text-xs text-surface-600">{{ isPhoto ? 'PNG or JPEG · up to 50 MB' : 'PDF, Word, Excel, PowerPoint, images or text · up to 50 MB' }}</div>
          <v-btn class="mt-1.5" color="primary" variant="outlined" @click="picker?.click()">{{ file ? 'Choose another file' : 'Choose file' }}</v-btn>

          <input
            ref="picker"
            :accept="isPhoto ? IMAGE_ACCEPT : DOCUMENT_ACCEPT"
            aria-label="Choose a file"
            class="sr-only"
            data-testid="document-file"
            tabindex="-1"
            type="file"
            @change="onPick"
          >
        </div>

        <p v-if="fileError" class="m-0 mt-2 text-sm text-error" role="alert">{{ fileError }}</p>
      </div>

      <!-- 2. The file, and how far it has got -->
      <div v-if="file && !fileError" class="flex flex-col gap-2.5 rounded-card bg-surface-50 px-4 py-3.5">
        <div class="flex items-center gap-3">
          <v-icon class="shrink-0 text-surface-600" :icon="mdiFileDocumentOutline" size="28" />

          <div class="min-w-0 grow">
            <div class="truncate text-label text-surface-900">{{ file.name }}</div>
            <div class="text-xs tabular-nums text-surface-600">{{ progressText }}</div>
          </div>

          <span v-if="upload" class="text-label tabular-nums text-surface-900">{{ pct }}%</span>

          <v-btn
            v-else
            :aria-label="`Remove ${file.name}`"
            icon
            size="36"
            variant="text"
            @click="clearFile"
          >
            <v-icon :icon="mdiClose" size="20" />
          </v-btn>
        </div>

        <div
          v-if="upload"
          :aria-label="paused ? `Paused: ${file.name}` : `Sending ${file.name}`"
          aria-valuemax="100"
          aria-valuemin="0"
          :aria-valuenow="pct"
          class="h-1.5 overflow-hidden rounded-full bg-surface-200"
          role="progressbar"
        >
          <div class="h-full rounded-full transition-[width]" :class="paused ? 'bg-warning' : 'bg-primary'" :style="{ width: `${pct}%` }" />
        </div>
      </div>

      <FeedbackBanner v-if="paused" :icon="mdiWifiOff" type="warning">
        <div class="font-semibold">No connection</div>
        <div>Nothing is lost. When you’re back online it carries on from {{ formatBytes(upload?.sent ?? 0) }} by itself.</div>
      </FeedbackBanner>

      <div v-if="!isPhoto" class="grid grid-cols-1 gap-3 sm:grid-cols-2" :class="locked ? 'opacity-75' : ''">
        <FormField id="ud-type" label="Type">
          <v-select
            id="ud-type"
            v-model="docType"
            :disabled="locked"
            item-title="label"
            item-value="value"
            :items="docTypes[scope]"
            name="doc_type"
          />
        </FormField>

        <FormField id="ud-version" label="Version label">
          <v-text-field
            id="ud-version"
            v-model="versionLabel"
            autocomplete="off"
            :disabled="locked"
            maxlength="60"
            name="version_label"
            placeholder="v1, Rev C… (optional)"
          />
        </FormField>
      </div>

      <FormField id="ud-title" :label="isPhoto ? 'Caption' : 'Title'">
        <v-text-field
          id="ud-title"
          v-model="title"
          autocomplete="off"
          :disabled="locked"
          :error-messages="titleError"
          maxlength="120"
          name="title"
          :placeholder="isPhoto ? 'What the photo shows' : 'Filled in from the file name'"
          @update:model-value="titleTouched = true"
        />
      </FormField>

      <FormField v-if="!isPhoto" id="ud-language" label="Language">
        <v-select
          id="ud-language"
          v-model="language"
          :disabled="locked"
          item-title="label"
          item-value="value"
          :items="languages"
          name="language"
        />
      </FormField>

      <!-- Staff-only unless someone turns this on (DOC-4, Q7) -->
      <div class="flex items-start gap-3 border-t border-surface-200 pt-3">
        <v-switch
          id="ud-share"
          v-model="clientVisible"
          class="shrink-0"
          color="primary"
          :disabled="locked"
          hide-details
          inset
          role="switch"
        />

        <div class="min-w-0 pt-1.5">
          <label class="text-label text-surface-900" for="ud-share">{{ shareLabel }}</label>
          <div class="mt-0.5 text-xs text-surface-600">{{ clientVisible ? 'On: they can download it once it has been checked.' : 'Off: only staff can see it. You can change this later.' }}</div>
        </div>
      </div>

      <div
        v-if="upload && !paused"
        class="flex items-center gap-2.5 rounded-md bg-info-container px-3 py-2.5 text-sm text-on-info-container"
        role="status"
      >
        <v-icon :icon="mdiInformationOutline" size="18" />
        <span>Keep this window open until it finishes. If the connection drops it carries on from where it stopped.</span>
      </div>

      <p v-if="paused" class="m-0 flex items-start gap-2.5 text-sm text-surface-700">
        <v-icon class="mt-0.5 shrink-0" :icon="mdiInformationOutline" size="18" />
        <span>If you close this page first, choose the same file again. It joins this upload and sends only what’s missing.</span>
      </p>

      <div class="mt-1 flex justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="cancel">{{ upload ? 'Cancel upload' : 'Cancel' }}</v-btn>

        <v-btn v-if="upload?.state === 'failed' || saveFailed" color="primary" variant="outlined" @click="retry">Try again</v-btn>
        <v-btn v-else-if="paused" color="primary" variant="outlined" @click="nudge">Try now</v-btn>

        <v-btn
          v-else
          color="primary"
          :disabled="!canSubmit"
          :loading="working"
          type="submit"
        >{{ working ? (saving ? 'Saving…' : 'Sending…') : 'Upload' }}</v-btn>
      </div>
    </form>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { DocScope } from './documents'
  import type { DocumentOut } from '@/api/models'
  import type { Upload } from '@/app/composables/useUpload'
  import { mdiClose, mdiFileDocumentOutline, mdiInformationOutline, mdiWifiOff } from '@mdi/js'
  import { computed, ref, watch } from 'vue'
  import { documentsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { useUploads } from '@/app/composables/useUpload'
  import { newId } from '@/app/ids'
  import { icons } from '@/app/theme/icons'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import {
    docTypes,
    DOCUMENT_ACCEPT,
    documentKind,
    fileProblem,
    formatBytes,
    IMAGE_ACCEPT,
    languages,
    percent,
    PHOTO_TYPE,
    titleFromFilename,
  } from './documents'

  // Upload a document to a station or a sensor model (DOC-1 to DOC-4). The file goes up in 8 MiB
  // parts straight to the files host (offline/upload.ts), then the document is made. It starts
  // staff-only. It needs a connection (OFF-10), and a dropped one never starts the file over.
  const props = defineProps<{
    scope: DocScope
    scopeId: string
    /** The station's or sensor model's name. */
    subject: string
    /** The station code. */
    code?: string | null
    /** The station's owner organization, for the "Show to …" switch. */
    orgName?: string | null
    /** A new version of this (the current one) rather than a first document. */
    replaces?: DocumentOut | null
    /** A photo of a sensor model (its gallery), not a document: pictures only, with a caption. */
    photo?: boolean
  }>()

  const open = defineModel<boolean>({ required: true })

  const emit = defineEmits<{
    saved: [document: DocumentOut]
  }>()

  const uploads = useUploads()

  const picker = ref<HTMLInputElement | null>(null)
  const dragging = ref(false)
  const file = ref<File | null>(null)
  const fileError = ref<string | null>(null)
  const upload = ref<Upload | null>(null)
  const error = ref<string | null>(null)
  const saving = ref(false)
  const saveFailed = ref(false)

  const docType = ref('other')
  const versionLabel = ref('')
  const title = ref('')
  const titleTouched = ref(false)
  const titleError = ref<string | undefined>()
  const language = ref('en')
  const clientVisible = ref(false)
  // One ID per document made in this dialog: a retry after a lost answer finds it, never makes two
  let documentId = newId()

  const isPhoto = computed(() => props.photo === true || props.replaces?.doc_type === PHOTO_TYPE)
  const heading = computed(() => {
    if (isPhoto.value) {
      return props.replaces ? 'Replace this photo' : 'Add a photo'
    }
    return props.replaces ? 'Upload a new version' : 'Upload a document'
  })

  const shareLabel = computed(() => props.scope === 'station'
    ? (props.orgName ? `Show to ${props.orgName}` : 'Show to the owner organization')
    : 'Show to clients who have this model installed')

  const working = computed(() => upload.value?.busy === true || saving.value)
  const locked = computed(() => working.value || upload.value?.state === 'failed' || saveFailed.value)
  const paused = computed(() => upload.value?.waiting === 'network' && working.value)
  const canSubmit = computed(() => file.value !== null && !fileError.value && !working.value)
  const pct = computed(() => upload.value ? percent(upload.value.sent, upload.value.total, upload.value.state === 'arrived' || saving.value) : 0)
  const progressText = computed(() => {
    const f = file.value
    if (!f) {
      return ''
    }
    const u = upload.value
    if (!u) {
      return formatBytes(f.size)
    }
    if (saving.value) {
      return 'Saving the document…'
    }
    if (u.phase === 'hashing') {
      return 'Preparing the file…'
    }
    return paused.value ? `${formatBytes(u.sent)} of ${formatBytes(f.size)} sent` : `${formatBytes(u.sent)} of ${formatBytes(f.size)}`
  })

  function reset (): void {
    file.value = null
    fileError.value = null
    error.value = null
    saving.value = false
    saveFailed.value = false
    upload.value = null
    versionLabel.value = ''
    title.value = props.replaces?.title ?? ''
    titleTouched.value = false
    titleError.value = undefined
    docType.value = props.replaces?.doc_type ?? (props.photo ? PHOTO_TYPE : docTypes[props.scope][0]!.value)
    language.value = props.replaces?.language ?? 'en'
    clientVisible.value = props.replaces?.client_visible ?? false
    documentId = newId()
  }

  watch(open, isOpen => {
    if (isOpen) {
      reset()
    }
  }, { immediate: true })

  function choose (picked: File | undefined): void {
    if (!picked) {
      return
    }
    fileError.value = fileProblem(picked, isPhoto.value ? 'photo' : 'document')
    file.value = picked
    if (!fileError.value && !titleTouched.value && !props.replaces) {
      title.value = titleFromFilename(picked.name)
    }
  }

  function onPick (event: Event): void {
    const input = event.target as HTMLInputElement
    choose(input.files?.[0])
    input.value = ''
  }

  function onDrop (event: DragEvent): void {
    dragging.value = false
    choose(event.dataTransfer?.files[0])
  }

  function clearFile (): void {
    file.value = null
    fileError.value = null
  }

  async function submit (): Promise<void> {
    const f = file.value
    if (!f || fileError.value || working.value) {
      return
    }
    titleError.value = undefined
    if (!title.value.trim()) {
      title.value = titleFromFilename(f.name)
    }
    if (!title.value.trim()) {
      titleError.value = isPhoto.value ? 'Give the photo a caption.' : 'Give the document a title.'
      return
    }
    error.value = null
    // Choosing the same file again after a close joins the open upload (the server finds it by
    // size and checksum), so a fresh `Upload` for the same file is safe
    upload.value = uploads.add(f, { ownerRef: `document:${props.scope}:${props.scopeId}`, kind: documentKind(f.name) })
    await run()
  }

  /** Send what is not on the server yet, then make the document. Safe to repeat: the upload
      resumes by its media ID and the document is made once, by its ID. */
  async function run (): Promise<void> {
    const current = upload.value
    if (!current) {
      return
    }
    error.value = null
    if (current.state !== 'arrived' && !(await current.start())) {
      if (current.state === 'failed') {
        error.value = current.error
      }
      return
    }
    await save(current)
  }

  async function save (done: Upload): Promise<void> {
    saving.value = true
    try {
      const saved = await documentsApi.create({
        id: documentId,
        scope: props.scope,
        scope_id: props.scopeId,
        doc_type: docType.value,
        title: title.value.trim(),
        version_label: versionLabel.value.trim() || null,
        language: language.value,
        client_visible: clientVisible.value,
        media_id: done.mediaId!,
        supersedes_id: props.replaces?.id ?? null,
      })
      emit('saved', saved)
      open.value = false
    } catch (error_) {
      error.value = error_ instanceof NetworkError
        ? 'The file is up, but the connection dropped before it was saved. Try again: it won’t be sent twice.'
        : (error_ instanceof ApiError ? error_.detail : 'The file is up, but the document could not be saved. Try again.')
      // The bytes are on the server: "Try again" only repeats the save
      saveFailed.value = true
    } finally {
      saving.value = false
    }
  }

  async function retry (): Promise<void> {
    const failed = upload.value
    if (!failed) {
      return
    }
    if (saveFailed.value) {
      saveFailed.value = false
      error.value = null
      await save(failed)
      return
    }
    failed.reset()
    await run()
  }

  function nudge (): void {
    // The engine already retries by itself; this wakes it when the person knows signal is back
    globalThis.dispatchEvent(new Event('online'))
  }

  async function cancel (): Promise<void> {
    const running = upload.value
    if (running) {
      await running.cancel()
      uploads.drop(running)
      upload.value = null
    }
    open.value = false
  }

  function onToggle (open: boolean): void {
    if (!open) {
      void cancel()
    }
  }
</script>
