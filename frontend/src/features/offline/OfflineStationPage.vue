<template>
  <PageBody :back="{ name: 'sync' }" :subtitle="found?.station.station.name" :title="found?.station.station.code ?? 'Station'">
    <div class="flex flex-col gap-4 p-4 md:p-0">
      <FeedbackBanner type="warning">No connection. Showing the copy prepared {{ ago }}.</FeedbackBanner>

      <div v-if="loading" aria-label="Loading the station…" class="flex flex-col gap-3" role="status">
        <v-skeleton-loader type="heading, list-item-two-line, list-item-two-line" />
      </div>

      <ScanCard v-else-if="!found" :icon="mdiMapMarkerOffOutline" title="This station is not on your phone" tone="neutral">
        Open it with a connection, or prepare a visit that includes it before you go.
        <template #actions>
          <v-btn block color="primary" size="large" :to="{ name: 'scan' }">Scan another label</v-btn>
        </template>
      </ScanCard>

      <template v-else>
        <section aria-labelledby="os-facts-h" class="flex flex-col gap-2 rounded-card bg-surface-50 p-4">
          <h2 id="os-facts-h" class="sr-only">Details</h2>

          <dl class="m-0 grid grid-cols-[110px_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
            <dt class="text-surface-600">Time zone</dt>
            <dd class="m-0 text-surface-900">{{ station.time_zone }}</dd>

            <template v-if="station.latitude !== null && station.longitude !== null">
              <dt class="text-surface-600">Position</dt>
              <dd class="m-0 font-mono text-surface-900">{{ station.latitude.toFixed(4) }}, {{ station.longitude.toFixed(4) }}</dd>
            </template>

            <template v-if="station.access_notes">
              <dt class="text-surface-600">Getting in</dt>
              <dd class="m-0 whitespace-pre-line text-surface-900">{{ station.access_notes }}</dd>
            </template>
          </dl>
        </section>

        <section aria-labelledby="os-sensors-h" class="flex flex-col gap-2 rounded-card bg-surface-50 p-4">
          <h2 id="os-sensors-h" class="m-0 text-h3 text-surface-900">Sensors</h2>
          <p v-if="station.installed.length === 0" class="m-0 text-sm text-surface-600">No sensors are installed here.</p>

          <ul v-else class="m-0 flex list-none flex-col gap-3 p-0" role="list">
            <li v-for="unit in station.installed" :key="unit.unit_id" class="flex items-center justify-between gap-3">
              <div class="min-w-0">
                <div class="text-surface-900">{{ unit.parameter ?? 'Not set' }} · {{ unit.model.model }}</div>
                <div class="font-mono text-sm text-surface-600" translate="no">SN {{ unit.serial }}</div>
              </div>

              <CalibrationDueChip :due="unit.calibration_due_at" :state="dueOf(unit.due_state)" :time-zone="station.time_zone" />
            </li>
          </ul>
        </section>

        <section aria-labelledby="os-config-h" class="flex flex-col gap-2 rounded-card bg-surface-50 p-4">
          <div class="flex items-baseline justify-between gap-3">
            <h2 id="os-config-h" class="m-0 text-h3 text-surface-900">Configuration</h2>
            <span v-if="found.station.config_version" class="text-sm text-surface-600">Version {{ found.station.config_version.version }}</span>
          </div>

          <p v-if="!found.station.config_version" class="m-0 text-sm text-surface-600">No configuration has been saved for this station.</p>

          <ul v-else class="m-0 flex list-none flex-col gap-1 p-0" role="list">
            <li v-for="file in found.station.config_version.files" :key="file.media_id" class="flex min-h-12 items-center gap-3">
              <div class="min-w-0 grow">
                <div class="truncate font-mono text-sm text-surface-900" translate="no">{{ file.filename }}</div>
                <div class="text-sm text-surface-600">{{ formatBytes(file.size_bytes) }} · {{ files.has(file.media_id) ? 'saved on this phone' : 'not on this phone' }}</div>
              </div>

              <v-btn
                v-if="files.has(file.media_id)"
                :aria-label="`Open ${file.filename}`"
                size="small"
                variant="outlined"
                @click="open(file.media_id)"
              >Open</v-btn>
            </li>
          </ul>
        </section>

        <section aria-labelledby="os-docs-h" class="flex flex-col gap-2 rounded-card bg-surface-50 p-4">
          <h2 id="os-docs-h" class="m-0 text-h3 text-surface-900">Documents</h2>
          <p v-if="documents.length === 0" class="m-0 text-sm text-surface-600">No documents for this station.</p>

          <ul v-else class="m-0 flex list-none flex-col gap-1 p-0" role="list">
            <li v-for="doc in documents" :key="doc.id" class="flex min-h-12 items-center gap-3">
              <div class="min-w-0 grow">
                <div class="truncate text-surface-900">{{ doc.title }}</div>
                <div class="text-sm text-surface-600">{{ formatBytes(doc.size_bytes) }} · {{ doc.media_id && files.has(doc.media_id) ? 'on this phone' : 'needs a connection' }}</div>
              </div>

              <v-btn
                v-if="doc.media_id && files.has(doc.media_id)"
                :aria-label="`Open ${doc.title}`"
                size="small"
                variant="outlined"
                @click="open(doc.media_id)"
              >Open</v-btn>
            </li>
          </ul>
        </section>
      </template>
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { DocumentOut } from '@/api/models'
  import type { DueState } from '@/features/stations/stations'
  import type { LocalFile } from '@/offline/db'
  import type { PreparedStation } from '@/offline/prepared'
  import { mdiMapMarkerOffOutline } from '@mdi/js'
  import { computed, onMounted, ref } from 'vue'
  import CalibrationDueChip from '@/components/CalibrationDueChip.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import ScanCard from '@/features/scan/ScanCard.vue'
  import { formatBytes } from '@/features/stations/documents'
  import { preparedStation, storedFiles } from '@/offline/prepared'
  import { useSessionStore } from '@/stores/session'
  import { openStoredFile } from './openStoredFile'
  import { preparedAgo } from './preparedAgo'

  // A station from the visit prepared on this phone (QR-5, CFG-4; W13-13): what the bundle held, with
  // the configuration files and documents that came with it. Read only; no network is used.
  const props = defineProps<{ id: string }>()
  const session = useSessionStore()

  const loading = ref(true)
  const found = ref<PreparedStation | null>(null)
  const files = ref(new Map<string, LocalFile>())

  const station = computed(() => found.value!.station.station)
  const documents = computed<DocumentOut[]>(() => {
    const docs = found.value?.station.documents
    return docs ? [...docs.station, ...docs.models.flatMap(m => m.documents)] : []
  })
  const ago = computed(() => (found.value ? preparedAgo(found.value.prepared.row.prepared_at) : 'earlier'))

  function dueOf (state: string | null): DueState | null {
    return state as DueState | null
  }

  function open (mediaId: string): void {
    const file = files.value.get(mediaId)
    if (file) {
      openStoredFile(file)
    }
  }

  onMounted(async () => {
    const me = session.user
    if (me) {
      found.value = await preparedStation(me.id, props.id)
      if (found.value) {
        files.value = await storedFiles(me.id, found.value.prepared.row.visit_id)
      }
    }
    loading.value = false
  })
</script>
