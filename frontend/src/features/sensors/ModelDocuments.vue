<template>
  <section aria-labelledby="docs-h">
    <div class="mb-2.5 flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <h2 id="docs-h" class="m-0 flex items-center gap-2 text-h3 text-surface-900">Datasheets and manuals<span v-if="docs && docs.length > 0" class="rounded bg-surface-100 px-2 py-0.5 text-xs font-normal text-surface-700">{{ docs.length }} {{ docs.length === 1 ? 'file' : 'files' }}</span></h2>
        <p class="m-0 mt-0.5 text-sm text-surface-600">Shown on every station that has this model installed. A client sees one only while the model is installed at one of their stations, and only if you mark it.</p>
      </div>

      <v-btn
        v-if="canWrite"
        color="primary"
        :prepend-icon="icons.upload"
        variant="tonal"
        @click="startUpload(null)"
      >Upload document</v-btn>
    </div>

    <FeedbackBanner v-if="error" type="error">{{ error }}</FeedbackBanner>

    <div v-else-if="docs === null" aria-label="Loading documents…" role="status">
      <v-skeleton-loader v-for="n in 2" :key="n" type="list-item-two-line" />
    </div>

    <p v-else-if="docs.length === 0" class="m-0 py-6 text-center text-surface-600">No documents for this model yet.</p>

    <ul v-else :aria-label="`Documents for ${model.manufacturer} ${model.model}`" class="m-0 grid list-none grid-cols-1 gap-2.5 p-0 md:grid-cols-2">
      <li v-for="doc in docs" :key="doc.id" class="flex items-center gap-3 rounded-card bg-surface-50 px-3.5 py-3">
        <span class="flex size-11 shrink-0 items-center justify-center rounded-lg bg-surface-100">
          <v-icon :class="fileIcon(doc.filename).tone" :icon="fileIcon(doc.filename).icon" size="26" />
        </span>

        <div class="min-w-0 grow">
          <div class="truncate font-medium" :class="docState(doc) === 'ready' ? 'text-surface-900' : 'text-surface-600'">{{ doc.title }}</div>

          <div class="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-surface-600">
            <span class="font-semibold uppercase text-primary">{{ docTypeLabel(doc.doc_type) }}</span>
            <span aria-hidden="true">·</span>
            <span class="font-mono" translate="no">{{ formatBytes(doc.size_bytes) }}</span>

            <template v-if="doc.version_label">
              <span aria-hidden="true">·</span>
              <span class="font-mono" translate="no">{{ doc.version_label }}</span>
            </template>

            <span aria-hidden="true">·</span>

            <span class="inline-flex items-center gap-1">
              <v-icon :icon="doc.client_visible ? mdiEyeOutline : mdiLockOutline" size="14" />{{ doc.client_visible ? 'Clients can see it' : 'Staff only' }}
            </span>
          </div>

          <DocumentStateNote :doc="doc" />
        </div>

        <div class="flex shrink-0 items-center">
          <v-btn
            v-if="isDownloadable(doc)"
            :aria-label="`Download ${doc.title}`"
            icon
            size="40"
            variant="text"
            @click="download(doc)"
          >
            <v-icon class="text-primary" :icon="icons.download" size="20" />
          </v-btn>

          <span v-else class="pr-2 text-xs text-surface-500">{{ docState(doc) === 'failed' ? 'Failed' : 'Not ready' }}</span>

          <DocumentMenu
            v-if="canWrite"
            :doc="doc"
            org-name="clients"
            @edit="startEdit(doc)"
            @new-version="startUpload(doc)"
            @visibility="setVisible(doc, $event)"
          />
        </div>
      </li>
    </ul>

    <UploadDialog
      v-if="canWrite"
      v-model="uploading"
      :replaces="replacing"
      scope="model"
      :scope-id="model.id"
      :subject="`${model.manufacturer} ${model.model}`"
      @saved="load(true)"
    />

    <DocumentDetailsDialog
      v-if="canWrite"
      v-model="editOpen"
      :doc="editing"
      @reload="load(true)"
      @saved="load(true)"
    />
  </section>
</template>

<script lang="ts" setup>
  import type { DocumentOut, SensorModelOut } from '@/api/models'
  import { mdiEyeOutline, mdiLockOutline } from '@mdi/js'
  import { computed, onBeforeUnmount, ref, watch } from 'vue'
  import { documentsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { icons } from '@/app/theme/icons'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import DocumentDetailsDialog from '@/features/stations/DocumentDetailsDialog.vue'
  import DocumentMenu from '@/features/stations/DocumentMenu.vue'
  import { docState, docTypeLabel, fileIcon, formatBytes, isDownloadable, openDownload, PHOTO_TYPE } from '@/features/stations/documents'
  import DocumentStateNote from '@/features/stations/DocumentStateNote.vue'
  import UploadDialog from '@/features/stations/UploadDialog.vue'

  // A sensor model's datasheets and manuals (DOC-1, DOC-3, DOC-4), on the Sensors page. Staff only.
  const props = defineProps<{
    model: SensorModelOut
    canWrite: boolean
  }>()

  const docs = ref<DocumentOut[] | null>(null)
  const error = ref<string | null>(null)
  const uploading = ref(false)
  const replacing = ref<DocumentOut | null>(null)
  const editing = ref<DocumentOut | null>(null)
  const editOpen = ref(false)
  const checking = computed(() => (docs.value ?? []).some(d => docState(d) === 'checking'))

  function wording (caught: unknown, action: string): string {
    if (caught instanceof NetworkError) {
      return 'This needs a connection. It will work when you have signal.'
    }
    return caught instanceof ApiError ? caught.detail : `We couldn’t ${action}. Reload the page to try again.`
  }

  async function load (quiet = false): Promise<void> {
    if (!quiet) {
      error.value = null
    }
    const id = props.model.id
    try {
      const page = await documentsApi.list({ scope: 'model', scope_id: id, limit: 200 })
      if (id === props.model.id) {
        docs.value = page.items.filter(d => d.doc_type !== PHOTO_TYPE)
        error.value = null
      }
    } catch (error_) {
      if (!quiet) {
        error.value = wording(error_, 'load the documents')
      }
    }
  }

  // Look again while media is still checking a file (five minutes at most)
  let timer: ReturnType<typeof setTimeout> | undefined
  let polls = 0
  function schedule (): void {
    clearTimeout(timer)
    if (!checking.value || polls >= 75) {
      return
    }
    timer = setTimeout(async () => {
      polls++
      if (!document.hidden) {
        await load(true)
      }
      schedule()
    }, 4000)
  }

  watch(() => props.model.id, () => {
    docs.value = null
    polls = 0
    void load()
  }, { immediate: true })
  watch(checking, () => {
    polls = 0
    schedule()
  })
  onBeforeUnmount(() => clearTimeout(timer))

  function startUpload (replaces: DocumentOut | null): void {
    replacing.value = replaces
    uploading.value = true
  }

  function startEdit (doc: DocumentOut): void {
    editing.value = doc
    editOpen.value = true
  }

  async function download (doc: DocumentOut): Promise<void> {
    error.value = null
    try {
      await openDownload(doc.filename, inline => documentsApi.download(doc.id, inline))
    } catch (error_) {
      error.value = wording(error_, 'open that file')
    }
  }

  async function setVisible (doc: DocumentOut, visible: boolean): Promise<void> {
    error.value = null
    try {
      await documentsApi.update(doc.id, { version: doc.version, client_visible: visible })
    } catch (error_) {
      error.value = error_ instanceof ApiError && error_.status === 409
        ? 'Someone changed this document first. The list has been refreshed: try again.'
        : wording(error_, 'change who sees that document')
    }
    await load(true)
  }
</script>
