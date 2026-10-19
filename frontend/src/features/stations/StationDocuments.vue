<template>
  <div class="flex flex-col gap-8">
    <FeedbackBanner v-if="error" type="error">{{ error }}</FeedbackBanner>

    <div v-if="docs === null && !error" aria-label="Loading documents…" role="status">
      <v-skeleton-loader v-for="n in 3" :key="n" type="list-item-two-line" />
    </div>

    <template v-if="docs">
      <!-- This station's own documents -->
      <section aria-labelledby="own-h">
        <div class="mb-2.5 flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <h2 id="own-h" class="m-0 text-h3 text-surface-900">{{ isStaff ? 'This station’s documents' : 'Documents for this station' }}</h2>
            <p v-if="isStaff" class="m-0 mt-0.5 text-sm text-surface-600">Installation records, site drawings and other files for this station only. Only the newest version of each is listed.</p>
          </div>

          <v-btn
            v-if="canWrite"
            color="primary"
            :prepend-icon="icons.upload"
            @click="startUpload(null)"
          >Upload document</v-btn>
        </div>

        <p v-if="docs.station.length === 0" class="m-0 py-8 text-center text-surface-600">
          {{ isStaff ? 'No documents yet.' : 'There are no documents for this station yet.' }}
        </p>

        <!-- From 768 px: a table -->
        <div v-else-if="mdAndUp" class="overflow-x-auto">
          <table class="w-full border-collapse text-sm">
            <caption class="sr-only">Documents for {{ station.name }}</caption>

            <thead>
              <tr class="bg-surface-100 text-left">
                <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Document</th>
                <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Type</th>
                <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Version</th>
                <th v-if="isStaff" class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Who sees it</th>
                <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">{{ isStaff ? 'Added' : 'Updated' }}</th>
                <th class="w-24 px-2 py-3" scope="col"><span class="sr-only">Actions</span></th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="doc in docs.station" :key="doc.id" class="h-16 border-t border-surface-200">
                <td class="px-4 py-2">
                  <div class="flex items-center gap-3">
                    <v-icon class="shrink-0" :class="fileIcon(doc.filename).tone" :icon="fileIcon(doc.filename).icon" size="28" />

                    <div class="min-w-0">
                      <div class="font-medium" :class="docState(doc) === 'ready' ? 'text-surface-900' : 'text-surface-600'">{{ doc.title }}</div>
                      <div class="font-mono text-xs text-surface-600" translate="no">{{ doc.filename }} · {{ formatBytes(doc.size_bytes) }}</div>
                      <DocumentStateNote :doc="doc" />
                    </div>
                  </div>
                </td>

                <td class="px-4 text-surface-900">{{ docTypeLabel(doc.doc_type) }}</td>
                <td class="whitespace-nowrap px-4 tabular-nums text-surface-900">{{ versionText(doc) }}</td>

                <td v-if="isStaff" class="px-4"><VisibilityChip :doc="doc" :org-name="station.owner_org_name" /></td>

                <td class="whitespace-nowrap px-4 tabular-nums text-surface-600">
                  <div class="text-surface-900">{{ formatListTime(doc.created_at, station.time_zone) }}</div>
                  <div v-if="isStaff && doc.uploaded_by" class="text-xs">{{ doc.uploaded_by }}</div>
                </td>

                <td class="whitespace-nowrap px-2 text-right">
                  <template v-if="isDownloadable(doc)">
                    <v-btn
                      v-if="isStaff"
                      :aria-label="`Download ${doc.title}`"
                      icon
                      size="40"
                      variant="text"
                      @click="download(doc)"
                    >
                      <v-icon class="text-surface-700" :icon="icons.download" size="20" />
                    </v-btn>

                    <v-btn
                      v-else
                      class="text-primary"
                      :prepend-icon="icons.download"
                      variant="text"
                      @click="download(doc)"
                    >Download</v-btn>
                  </template>

                  <span v-else class="pr-2 text-xs text-surface-500">{{ docState(doc) === 'failed' ? 'Failed' : 'Not ready' }}</span>

                  <DocumentMenu
                    v-if="canWrite"
                    :doc="doc"
                    :org-name="station.owner_org_name"
                    @edit="startEdit(doc)"
                    @new-version="startUpload(doc)"
                    @visibility="setVisible(doc, $event)"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Phones: a list; a row opens the file -->
        <ul v-else :aria-label="`Documents for ${station.name}`" class="m-0 flex list-none flex-col p-0">
          <li v-for="doc in docs.station" :key="doc.id" class="flex items-start gap-3 border-t border-surface-200 py-3 first:border-t-0">
            <v-icon class="mt-0.5 shrink-0" :class="fileIcon(doc.filename).tone" :icon="fileIcon(doc.filename).icon" size="28" />

            <div class="min-w-0 grow">
              <div class="font-medium" :class="docState(doc) === 'ready' ? 'text-surface-900' : 'text-surface-600'">{{ doc.title }}</div>
              <div class="text-sm text-surface-600">{{ docTypeLabel(doc.doc_type) }}<template v-if="doc.version_label"> · {{ doc.version_label }}</template> · {{ formatListTime(doc.created_at, station.time_zone) }}</div>
              <div v-if="isStaff" class="mt-1"><VisibilityChip :doc="doc" :org-name="station.owner_org_name" /></div>
              <DocumentStateNote :doc="doc" />
            </div>

            <v-btn
              v-if="isDownloadable(doc)"
              :aria-label="`Open ${doc.title}`"
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
              :org-name="station.owner_org_name"
              @edit="startEdit(doc)"
              @new-version="startUpload(doc)"
              @visibility="setVisible(doc, $event)"
            />
          </li>
        </ul>
      </section>

      <!-- Manuals that belong to the sensor models installed here -->
      <section v-if="models.length > 0 || isStaff" aria-labelledby="models-h">
        <h2 id="models-h" class="m-0 text-h3 text-surface-900">Manuals for the sensors installed here</h2>

        <p class="m-0 mt-0.5 mb-2 text-sm text-surface-600">
          {{ isStaff ? 'These belong to the sensor model and show on every station that uses it. Add or change them in the catalogue under Sensors.' : 'They come from the makers of the equipment at this station.' }}
        </p>

        <p v-if="docs.models.length === 0" class="m-0 text-sm text-surface-600">No sensors are installed here.</p>

        <ul v-else class="m-0 flex list-none flex-col border-t border-surface-200 p-0">
          <li
            v-for="m in models"
            :key="m.model_id"
            class="flex min-h-14 flex-wrap items-center gap-x-3 gap-y-1 border-b border-surface-200 py-2"
          >
            <v-icon class="shrink-0 text-surface-600" :icon="icons.sensor" size="20" />
            <div class="min-w-0 grow basis-52"><span class="font-medium text-surface-900">{{ m.manufacturer }} {{ m.model }}</span></div>

            <div class="flex flex-wrap items-center">
              <template v-if="m.documents.length > 0">
                <v-btn
                  v-for="d in m.documents"
                  :key="d.id"
                  class="text-primary"
                  :disabled="!isDownloadable(d)"
                  :title="d.title"
                  variant="text"
                  @click="download(d)"
                >{{ docTypeLabel(d.doc_type) }}</v-btn>
              </template>

              <span v-else class="px-2 text-sm text-surface-500">No documents yet</span>
            </div>
          </li>
        </ul>
      </section>
    </template>

    <UploadDialog
      v-model="uploading"
      :code="station.code"
      :org-name="station.owner_org_name"
      :replaces="replacing"
      scope="station"
      :scope-id="station.id"
      :subject="station.name"
      @saved="onSaved"
    />

    <DocumentDetailsDialog
      v-if="canWrite"
      v-model="editOpen"
      :doc="editing"
      @reload="onSaved"
      @saved="onSaved"
    />
  </div>
</template>

<script lang="ts" setup>
  import type { DocumentOut, StationDetail, StationDocuments } from '@/api/models'
  import { computed, onBeforeUnmount, ref, watch } from 'vue'
  import { useDisplay } from 'vuetify'
  import { documentsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { formatListTime } from '@/app/format'
  import { icons } from '@/app/theme/icons'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import DocumentDetailsDialog from './DocumentDetailsDialog.vue'
  import DocumentMenu from './DocumentMenu.vue'
  import { docState, docTypeLabel, fileIcon, formatBytes, isDownloadable, openDownload, versionText } from './documents'
  import DocumentStateNote from './DocumentStateNote.vue'
  import UploadDialog from './UploadDialog.vue'
  import VisibilityChip from './VisibilityChip.vue'

  // The station page's Documents tab (PRD DOC-1 to DOC-4): the station's own documents and the
  // manuals of the sensor models installed here. A client sees the clean, client-visible ones only
  // (the server filters them: rule 6). A new file reads "Checking file…" until media has checked it.
  const props = defineProps<{
    station: StationDetail
    isStaff: boolean
    /** Technicians and admins; viewers never mutate (rule 5). */
    canWrite: boolean
  }>()

  const { mdAndUp } = useDisplay()

  const docs = ref<StationDocuments | null>(null)
  const error = ref<string | null>(null)
  const uploading = ref(false)
  const replacing = ref<DocumentOut | null>(null)
  const editing = ref<DocumentOut | null>(null)
  const editOpen = ref(false)

  /** Clients see only the models that have something for them. */
  const models = computed(() => (docs.value?.models ?? []).filter(m => props.isStaff || m.documents.length > 0))

  const everything = computed(() => [...(docs.value?.station ?? []), ...(docs.value?.models.flatMap(m => m.documents) ?? [])])
  const checking = computed(() => everything.value.some(d => docState(d) === 'checking'))

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
    const id = props.station.id
    try {
      const result = await documentsApi.forStation(id)
      if (id === props.station.id) {
        docs.value = result
        error.value = null
      }
    } catch (error_) {
      if (!quiet) {
        error.value = wording(error_, 'load the documents')
      }
    }
  }

  // Media's checks take a few seconds: look again until nothing is waiting (for five minutes at most)
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

  watch(() => props.station.id, () => {
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

  async function onSaved (): Promise<void> {
    await load(true)
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
      await load(true)
    } catch (error_) {
      error.value = error_ instanceof ApiError && error_.status === 409
        ? 'Someone changed this document first. The list has been refreshed: try again.'
        : wording(error_, 'change who sees that document')
      await load(true)
    }
  }
</script>
