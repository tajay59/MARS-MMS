<template>
  <section aria-labelledby="docs-h">
    <div class="mb-2.5 flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <h2 id="docs-h" class="m-0 text-h3 text-surface-900">Datasheets and manuals</h2>
        <p class="m-0 mt-0.5 text-sm text-surface-600">Shown on every station that has this model installed. A client sees one only while the model is installed at one of their stations, and only if you mark it.</p>
      </div>

      <v-btn v-if="canWrite" color="primary" :prepend-icon="icons.upload" @click="startUpload(null)">Upload document</v-btn>
    </div>

    <FeedbackBanner v-if="error" type="error">{{ error }}</FeedbackBanner>

    <div v-else-if="docs === null" aria-label="Loading documents…" role="status">
      <v-skeleton-loader v-for="n in 2" :key="n" type="list-item-two-line" />
    </div>

    <p v-else-if="docs.length === 0" class="m-0 py-6 text-center text-surface-600">No documents for this model yet.</p>

    <div v-else-if="mdAndUp" class="overflow-x-auto">
      <table class="w-full border-collapse text-sm">
        <caption class="sr-only">Documents for {{ model.manufacturer }} {{ model.model }}</caption>

        <thead>
          <tr class="bg-surface-100 text-left">
            <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Document</th>
            <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Type</th>
            <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Language</th>
            <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Clients</th>
            <th class="w-24 px-2 py-3" scope="col"><span class="sr-only">Actions</span></th>
          </tr>
        </thead>

        <tbody>
          <tr v-for="doc in docs" :key="doc.id" class="h-16 border-t border-surface-200">
            <td class="px-4 py-2">
              <div class="flex items-center gap-3">
                <v-icon class="shrink-0" :class="fileIcon(doc.filename).tone" :icon="fileIcon(doc.filename).icon" size="28" />

                <div class="min-w-0">
                  <div class="font-medium" :class="docState(doc) === 'ready' ? 'text-surface-900' : 'text-surface-600'">{{ doc.title }}</div>
                  <div class="font-mono text-xs text-surface-600" translate="no">{{ doc.version_label ? `${doc.version_label} · ` : '' }}{{ formatBytes(doc.size_bytes) }}</div>
                  <DocumentStateNote :doc="doc" />
                </div>
              </div>
            </td>

            <td class="px-4 text-surface-900">{{ docTypeLabel(doc.doc_type) }}</td>
            <td class="px-4 text-surface-900">{{ languageLabel(doc.language) }}</td>

            <td class="px-4">
              <span class="inline-flex h-6 items-center gap-1.25 whitespace-nowrap rounded-full px-2.5 text-xs font-medium" :class="doc.client_visible ? 'bg-primary-100 text-primary-800' : 'bg-surface-100 text-surface-700'">
                <v-icon :icon="doc.client_visible ? mdiEyeOutline : mdiLockOutline" size="14" />{{ doc.client_visible ? 'Can see it' : 'Staff only' }}
              </span>
            </td>

            <td class="whitespace-nowrap px-2 text-right">
              <v-btn
                v-if="isDownloadable(doc)"
                :aria-label="`Download ${doc.title}`"
                icon
                size="40"
                variant="text"
                @click="download(doc)"
              >
                <v-icon class="text-surface-700" :icon="icons.download" size="20" />
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
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <ul v-else :aria-label="`Documents for ${model.manufacturer} ${model.model}`" class="m-0 flex list-none flex-col p-0">
      <li v-for="doc in docs" :key="doc.id" class="flex items-start gap-3 border-t border-surface-200 py-3 first:border-t-0">
        <v-icon class="mt-0.5 shrink-0" :class="fileIcon(doc.filename).tone" :icon="fileIcon(doc.filename).icon" size="28" />

        <div class="min-w-0 grow">
          <div class="font-medium" :class="docState(doc) === 'ready' ? 'text-surface-900' : 'text-surface-600'">{{ doc.title }}</div>
          <div class="text-sm text-surface-600">{{ docTypeLabel(doc.doc_type) }} · {{ languageLabel(doc.language) }} · {{ doc.client_visible ? 'Clients can see it' : 'Staff only' }}</div>
          <DocumentStateNote :doc="doc" />
        </div>

        <v-btn
          v-if="isDownloadable(doc)"
          :aria-label="`Download ${doc.title}`"
          icon
          size="40"
          variant="text"
          @click="download(doc)"
        >
          <v-icon class="text-surface-700" :icon="icons.download" size="20" />
        </v-btn>

        <DocumentMenu
          v-if="canWrite"
          :doc="doc"
          org-name="clients"
          @edit="startEdit(doc)"
          @new-version="startUpload(doc)"
          @visibility="setVisible(doc, $event)"
        />
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
  import { useDisplay } from 'vuetify'
  import { documentsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { icons } from '@/app/theme/icons'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import DocumentDetailsDialog from '@/features/stations/DocumentDetailsDialog.vue'
  import DocumentMenu from '@/features/stations/DocumentMenu.vue'
  import { docState, docTypeLabel, fileIcon, formatBytes, isDownloadable, languageLabel, openDownload } from '@/features/stations/documents'
  import DocumentStateNote from '@/features/stations/DocumentStateNote.vue'
  import UploadDialog from '@/features/stations/UploadDialog.vue'

  // A sensor model's datasheets and manuals (DOC-1, DOC-3, DOC-4), on the Sensors page. Staff only.
  const props = defineProps<{
    model: SensorModelOut
    canWrite: boolean
  }>()

  const { mdAndUp } = useDisplay()

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
        docs.value = page.items
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
