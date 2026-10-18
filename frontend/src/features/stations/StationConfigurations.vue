<template>
  <div class="flex flex-col gap-4">
    <FeedbackBanner v-if="error" type="error">{{ error }}</FeedbackBanner>

    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <h2 class="m-0 text-h3 text-surface-900">Configuration versions</h2>
        <p class="m-0 mt-0.5 text-sm text-surface-600">Every version is kept for good. Files can’t be changed or deleted once a version is saved.</p>
      </div>

      <v-btn v-if="canWrite" color="primary" :prepend-icon="mdiPlus" @click="creating = true">New version</v-btn>
    </div>

    <div v-if="versions === null && !error" aria-label="Loading configurations…" role="status">
      <v-skeleton-loader v-for="n in 3" :key="n" type="list-item-three-line" />
    </div>

    <p v-else-if="versions && versions.length === 0" class="m-0 py-8 text-center text-surface-600">
      No configuration has been saved for this station yet.
    </p>

    <div v-else-if="versions" class="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
      <!-- Versions, newest first -->
      <ol aria-label="Versions, newest first" class="m-0 flex list-none flex-col gap-0.5 p-0">
        <li v-for="v in versions" :key="v.id">
          <button
            :aria-current="v.version === shownNumber ? 'true' : undefined"
            class="flex w-full flex-col gap-0.5 rounded-md px-3 py-2.5 text-left"
            :class="v.version === shownNumber ? 'bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100' : 'text-surface-900 hover:bg-surface-100'"
            type="button"
            @click="show(v.version)"
          >
            <span class="flex items-center gap-2 text-label">
              Version {{ v.version }}
              <span v-if="v.version === latest" class="inline-flex h-5 items-center rounded-full bg-success-container px-2 text-xs font-medium text-on-success-container">Current</span>
            </span>

            <span class="text-xs tabular-nums" :class="v.version === shownNumber ? '' : 'text-surface-600'">{{ formatDate(v.created_at, station.time_zone) }} · {{ v.created_by ?? 'Imported' }} · {{ v.files.length }} {{ v.files.length === 1 ? 'file' : 'files' }}</span>
            <span v-if="v.notes" class="line-clamp-2 text-sm" :class="v.version === shownNumber ? '' : 'text-surface-700'">{{ v.notes }}</span>
          </button>
        </li>
      </ol>

      <!-- The version shown, against another -->
      <section v-if="shown" :aria-labelledby="`cv-${shown.version}-h`" class="min-w-0">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 :id="`cv-${shown.version}-h`" class="m-0 text-h3 text-surface-900">Version {{ shown.version }}</h3>

            <p class="m-0 mt-0.5 text-sm text-surface-600">
              Saved {{ formatDateTime(shown.created_at, station.time_zone) }}<template v-if="shown.created_by"> by {{ shown.created_by }}</template><template v-if="shown.notes"> · {{ shown.notes }}</template>
            </p>
          </div>

          <v-select
            v-if="others.length > 0"
            v-model="againstNumber"
            aria-label="Compare with"
            class="max-w-48"
            item-title="title"
            item-value="value"
            :items="others"
            label="Compare with"
            @update:model-value="loadDiff"
          />
        </div>

        <div v-if="against" aria-label="Changes since the version compared" class="mt-3 flex flex-wrap gap-2" role="group">
          <span v-for="c in summary" :key="c.change" class="inline-flex h-6 items-center rounded-full px-2.5 text-xs font-medium" :class="changeLook[c.change].chip">
            {{ c.count }} {{ c.change }}
          </span>
        </div>

        <div class="mt-3 overflow-x-auto">
          <table class="w-full border-collapse text-sm">
            <caption class="sr-only">Files in version {{ shown.version }}<template v-if="against"> compared with version {{ against.version }}</template></caption>

            <thead>
              <tr class="bg-surface-100 text-left">
                <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">File</th>
                <th v-if="against" class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Since version {{ against.version }}</th>
                <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Size</th>
                <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Checksum</th>
                <th class="w-16 px-2 py-3" scope="col"><span class="sr-only">Download</span></th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="row in rows" :key="`${row.change}-${row.filename}`" class="h-13 border-t border-surface-200">
                <td class="px-4">
                  <span class="inline-flex items-center gap-2.5" :class="row.change === 'removed' ? 'text-surface-600 line-through' : 'text-surface-900'">
                    <v-icon class="shrink-0 text-surface-600" :icon="fileIcon(row.filename).icon" size="20" />
                    <span class="font-mono text-[13px]" translate="no">{{ row.filename }}</span>
                  </span>
                </td>

                <td v-if="against" class="px-4">
                  <span v-if="row.change !== 'unchanged'" class="inline-flex h-6 items-center rounded-full px-2.5 text-xs font-medium" :class="changeLook[row.change].chip">{{ changeLook[row.change].label }}</span>
                  <span v-else class="text-surface-600">Unchanged</span>
                </td>

                <td class="whitespace-nowrap px-4 tabular-nums text-surface-900">{{ row.change === 'removed' ? `in version ${against?.version}` : formatBytes(row.size_bytes) }}</td>
                <td class="whitespace-nowrap px-4 font-mono text-xs text-surface-600" translate="no">{{ shortHash(row.sha256) }}</td>

                <td class="px-2 text-right">
                  <v-btn
                    v-if="row.change !== 'removed'"
                    :aria-label="`Download ${row.filename}`"
                    icon
                    size="40"
                    variant="text"
                    @click="download(row)"
                  >
                    <v-icon class="text-surface-700" :icon="icons.download" size="20" />
                  </v-btn>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <NewConfigDialog
      v-if="canWrite"
      v-model="creating"
      :next-version="nextVersion"
      :station="station"
      @saved="onSaved"
    />
  </div>
</template>

<script lang="ts" setup>
  import type { Change, FileRow } from './configs'
  import type { ConfigDiff, ConfigVersionOut, StationDetail } from '@/api/models'
  import { mdiPlus } from '@mdi/js'
  import { computed, ref, watch } from 'vue'
  import { mediaApi } from '@/api/media'
  import { configVersionsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { formatDate, formatDateTime } from '@/app/format'
  import { icons } from '@/app/theme/icons'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { changeCounts, changeLook, fileRows, nextVersionNumber, shortHash } from './configs'
  import { fileIcon, formatBytes } from './documents'
  import NewConfigDialog from './NewConfigDialog.vue'

  // The station page's Configurations tab (CFG-1 to CFG-3): staff only, clients never see it.
  // A version is written once. The table shows its files against the version before (or another).
  const props = defineProps<{
    station: StationDetail
    /** Technicians and admins (viewers never mutate, rule 5). */
    canWrite: boolean
  }>()

  const versions = ref<ConfigVersionOut[] | null>(null)
  const error = ref<string | null>(null)
  const creating = ref(false)
  const shownNumber = ref<number | null>(null)
  const againstNumber = ref<number | null>(null)
  const diff = ref<ConfigDiff | null>(null)

  const latest = computed(() => versions.value?.[0]?.version ?? null)
  const nextVersion = computed(() => nextVersionNumber(versions.value ?? []))
  const shown = computed(() => versions.value?.find(v => v.version === shownNumber.value) ?? null)
  const against = computed(() => againstNumber.value === null ? null : versions.value?.find(v => v.version === againstNumber.value) ?? null)
  const others = computed(() => (versions.value ?? [])
    .filter(v => v.version !== shownNumber.value)
    .map(v => ({ value: v.version, title: `Version ${v.version}` })))
  const rows = computed<FileRow[]>(() => shown.value ? fileRows(shown.value, against.value, against.value ? diff.value : null) : [])
  const summary = computed(() => {
    const counts = changeCounts(rows.value)
    return (['changed', 'added', 'removed', 'unchanged'] as Change[]).map(change => ({ change, count: counts[change] })).filter(c => c.count > 0)
  })

  function wording (caught: unknown, action: string): string {
    if (caught instanceof NetworkError) {
      return 'This needs a connection. It will work when you have signal.'
    }
    return caught instanceof ApiError ? caught.detail : `We couldn’t ${action}. Reload the page to try again.`
  }

  async function load (): Promise<void> {
    error.value = null
    const id = props.station.id
    try {
      const list = await configVersionsApi.list(id)
      if (id === props.station.id) {
        versions.value = list
        const keep = list.some(v => v.version === shownNumber.value)
        show(keep ? shownNumber.value : (list[0]?.version ?? null))
      }
    } catch (error_) {
      error.value = wording(error_, 'load the configurations')
    }
  }

  /** Show a version against the one before it. */
  function show (version: number | null): void {
    shownNumber.value = version
    // The list is newest first, so the first one older than this is the version before it
    const before = version === null ? null : (versions.value?.find(v => v.version < version) ?? null)
    againstNumber.value = before?.version ?? null
    void loadDiff()
  }

  async function loadDiff (): Promise<void> {
    diff.value = null
    const version = shownNumber.value
    const base = againstNumber.value
    if (version === null || base === null) {
      return
    }
    try {
      const result = await configVersionsApi.diff(props.station.id, version, base)
      if (version === shownNumber.value && base === againstNumber.value) {
        diff.value = result
      }
    } catch (error_) {
      error.value = wording(error_, 'compare those versions')
    }
  }

  async function download (row: FileRow): Promise<void> {
    error.value = null
    try {
      const media = await mediaApi.get(row.media_id)
      const url = media.urls?.download
      if (!url) {
        throw new Error('no link')
      }
      globalThis.location.assign(url)
    } catch (error_) {
      error.value = wording(error_, 'download that file')
    }
  }

  async function onSaved (version: ConfigVersionOut): Promise<void> {
    shownNumber.value = version.version
    await load()
  }

  watch(() => props.station.id, () => {
    versions.value = null
    shownNumber.value = null
    againstNumber.value = null
    diff.value = null
    void load()
  }, { immediate: true })
</script>
