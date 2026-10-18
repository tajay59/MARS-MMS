<template>
  <PageBody
    :back="open ? { name: 'sensors', query: listQuery } : undefined"
    back-label="Back to the catalogue"
    :record="selected ? selected.id : null"
    :subtitle="selected ? undefined : summary"
    :title="selected ? `${selected.manufacturer} ${selected.model}` : 'Sensors'"
    :wide="!selected"
  >
    <template v-if="selected" #subtitle>
      <span>{{ kindLabel(selected.kind) }}</span>

      <span v-if="selected.parameters.length > 0">
        measures <ParameterTags :parameters="selected.parameters" />
      </span>

      <span v-if="selected.default_calibration_interval_days">calibrate every {{ selected.default_calibration_interval_days }} days</span>
    </template>

    <!-- The pane: search and kind of part -->
    <PaneContent>
      <div class="flex flex-col gap-3 px-3">
        <v-text-field
          aria-label="Search by make, model or parameter"
          autocomplete="off"
          class="px-1"
          clearable
          hide-details
          :model-value="filters.q"
          name="q"
          placeholder="Search make or model"
          :prepend-inner-icon="mdiMagnify"
          spellcheck="false"
          type="search"
          @update:model-value="setFilters({ q: ($event ?? '').trim() })"
        />

        <div aria-label="Filter by kind of part" class="-mx-3 flex gap-1.5 overflow-x-auto px-4 pb-1" role="group">
          <button
            v-for="k in kindFilters"
            :key="k.value"
            :aria-pressed="filters.kind === k.value"
            class="inline-flex h-8 shrink-0 items-center rounded-full border px-3 text-sm font-medium"
            :class="filters.kind === k.value ? 'border-transparent bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100' : 'border-surface-300 text-surface-900'"
            type="button"
            @click="setFilters({ kind: k.value })"
          >{{ k.label }}</button>
        </div>

        <p v-if="!loading && !loadError && shown.length === 0" class="m-0 px-2 text-sm text-surface-600">No models match.</p>

        <ul v-else aria-label="Sensor models" class="m-0 flex list-none flex-col gap-0.5 p-0">
          <li
            v-for="m in shown"
            :key="m.id"
            class="relative flex flex-col rounded-card px-3 py-2.5 transition-colors duration-150"
            :class="m.id === modelId ? 'bg-primary-50' : 'hover:bg-surface-100 active:bg-surface-200'"
          >
            <router-link
              :aria-current="m.id === modelId ? 'page' : undefined"
              class="truncate font-medium text-surface-900 no-underline after:absolute after:inset-0 after:rounded-card focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
              :to="{ name: 'sensors', params: { id: m.id }, query: listQuery }"
            >{{ m.manufacturer }} {{ m.model }}</router-link>

            <span class="truncate text-sm text-surface-600">{{ modelLine(m) }}</span>
          </li>
        </ul>
      </div>
    </PaneContent>

    <FeedbackBanner v-if="loadError" type="error">{{ loadError }}</FeedbackBanner>

    <div v-else-if="loading" aria-label="Loading the catalogue…" class="flex flex-col gap-2" role="status">
      <v-skeleton-loader v-for="n in 4" :key="n" type="list-item-two-line" />
    </div>

    <!-- The view: one model -->
    <div v-else-if="selected" class="flex flex-col gap-8">
      <ModelDocuments :can-write="canWrite" :model="selected" />

      <section aria-labelledby="units-h">
        <h2 id="units-h" class="m-0 mb-2 text-h3 text-surface-900">
          Units of this model<span v-if="units" class="font-normal text-surface-600"> · {{ units.length }}</span>
        </h2>

        <FeedbackBanner v-if="unitsError" type="error">{{ unitsError }}</FeedbackBanner>

        <div v-else-if="units === null" aria-label="Loading units…" role="status">
          <v-skeleton-loader type="list-item-two-line" />
        </div>

        <p v-else-if="units.length === 0" class="m-0 py-4 text-sm text-surface-600">No units of this model are registered yet.</p>

        <div v-else class="overflow-x-auto">
          <table class="w-full border-collapse text-sm">
            <caption class="sr-only">Units of {{ selected.manufacturer }} {{ selected.model }}</caption>

            <thead>
              <tr class="bg-surface-100 text-left">
                <th v-for="h in ['Serial', 'Status', 'Where', 'Calibration']" :key="h" class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">{{ h }}</th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="u in units" :key="u.id" class="h-13 border-t border-surface-200">
                <td class="whitespace-nowrap px-4 font-mono text-surface-900" translate="no">{{ u.serial }}</td>
                <td class="whitespace-nowrap px-4 text-surface-900">{{ unitStatusLabel[u.status] ?? u.status }}</td>

                <td class="px-4 text-surface-900">
                  <router-link v-if="u.station" class="text-primary no-underline hover:underline" :to="{ name: 'stations', params: { id: u.station.id }, query: { tab: 'sensors' } }">{{ whereLabel(u) }}</router-link>
                  <template v-else>{{ whereLabel(u) }}</template>
                </td>

                <td class="px-4"><CalibrationDueChip :due="u.calibration_due_at" :state="asDue(u.due_state)" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <!-- The view: nothing chosen yet (phones show the list alone) -->
    <div v-else-if="modelId" class="py-6">
      <FeedbackBanner type="info">That sensor model wasn’t found. Choose one from the list.</FeedbackBanner>
    </div>

    <div v-else class="flex flex-col items-center gap-2 py-14 text-center">
      <v-icon class="text-surface-500" :icon="icons.sensor" size="40" />
      <h2 class="m-0 text-h3 text-surface-900">Choose a sensor model</h2>
      <p class="m-0 max-w-sm text-sm text-surface-600">Its datasheets and manuals, and every unit of it, are here.</p>
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { SensorFilters } from './sensors'
  import type { SensorModelOut, SensorUnitOut } from '@/api/models'
  import type { DueState } from '@/features/stations/stations'
  import { mdiMagnify } from '@mdi/js'
  import { computed, onMounted, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { sensorModelsApi, sensorUnitsApi } from '@/api/operations'
  import { NetworkError } from '@/api/problem'
  import { usePaneSelection } from '@/app/shells/pane'
  import { icons } from '@/app/theme/icons'
  import CalibrationDueChip from '@/components/CalibrationDueChip.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import ParameterTags from '@/features/stations/ParameterTags.vue'
  import { kindLabel } from '@/features/stations/stations'
  import { useSessionStore } from '@/stores/session'
  import ModelDocuments from './ModelDocuments.vue'
  import { kindFilters, matchesModel, modelLine, sensorFiltersFrom, sensorQueryFrom, unitStatusLabel, whereLabel } from './sensors'

  // /sensors and /sensors/:id (AFD §3; PRD CAL-1, DOC-1): the catalogue of models with their
  // datasheets and manuals and the units of each. Staff only. A few dozen models at most, so the
  // page loads them all once and filters here.
  const session = useSessionStore()
  const route = useRoute()
  const router = useRouter()

  const models = ref<SensorModelOut[]>([])
  const loading = ref(true)
  const loadError = ref<string | null>(null)
  const units = ref<SensorUnitOut[] | null>(null)
  const unitsError = ref<string | null>(null)

  const modelId = computed(() => typeof route.params.id === 'string' && route.params.id ? route.params.id : null)
  const open = computed(() => modelId.value !== null)
  usePaneSelection(() => open.value)

  const canWrite = computed(() => session.hasAnyRole(['technician', 'admin']))
  const filters = computed(() => sensorFiltersFrom(route.query))
  const listQuery = computed(() => sensorQueryFrom(filters.value))
  const shown = computed(() => models.value.filter(m => matchesModel(m, filters.value)))
  const selected = computed(() => models.value.find(m => m.id === modelId.value) ?? null)
  const summary = computed(() => loading.value || loadError.value ? undefined : `${models.value.length} ${models.value.length === 1 ? 'model' : 'models'} in the catalogue`)

  function setFilters (patch: Partial<SensorFilters>): void {
    void router.replace({ query: { ...route.query, ...sensorQueryFrom({ ...filters.value, ...patch }) } })
  }

  function asDue (value: string | null): DueState | null {
    return (['overdue', 'due_soon', 'ok'] as const).find(state => state === value) ?? null
  }

  async function loadModels (): Promise<void> {
    loadError.value = null
    try {
      models.value = (await sensorModelsApi.list()).items
    } catch (error) {
      loadError.value = error instanceof NetworkError
        ? 'This needs a connection. It will load when you have signal.'
        : 'We couldn’t load the catalogue. Reload the page to try again.'
    } finally {
      loading.value = false
    }
  }

  async function loadUnits (id: string): Promise<void> {
    units.value = null
    unitsError.value = null
    try {
      const page = await sensorUnitsApi.list({ model_id: id, limit: 200 })
      if (id === modelId.value) {
        units.value = page.items
      }
    } catch (error) {
      unitsError.value = error instanceof NetworkError
        ? 'This needs a connection. It will load when you have signal.'
        : 'We couldn’t load the units. Reload the page to try again.'
    }
  }

  onMounted(loadModels)
  watch(modelId, id => {
    if (id) {
      void loadUnits(id)
    } else {
      units.value = null
    }
  }, { immediate: true })
</script>
