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

    <template v-if="selected && canWrite" #actions>
      <v-btn color="primary" :prepend-icon="mdiPencilOutline" variant="tonal" @click="editModel">Edit model</v-btn>
    </template>

    <!-- Phones: the button sits in the pinned header; from 768 px it is in the pane -->
    <template v-else-if="!open && !mdAndUp && canWrite && !loadError" #actions>
      <v-btn color="primary" :prepend-icon="mdiPlus" @click="addModel">Add a model</v-btn>
    </template>

    <!-- The pane: search and kind of part -->
    <PaneContent pin>
      <div class="flex flex-col gap-3 px-3">
        <v-text-field
          aria-label="Search by make, model or parameter"
          autocomplete="off"
          class="px-1"
          clearable
          hide-details
          :model-value="filters.q"
          name="q"
          placeholder="Search make, model or parameter"
          :prepend-inner-icon="mdiMagnify"
          spellcheck="false"
          type="search"
          @update:model-value="setFilters({ q: ($event ?? '').trim() })"
        />

        <v-btn
          v-if="canWrite && !loadError && mdAndUp"
          block
          color="primary"
          :prepend-icon="mdiPlus"
          @click="addModel"
        >Add a model</v-btn>

        <div aria-label="Filter the catalogue" class="-mx-3 flex gap-1.5 overflow-x-auto px-4 pb-3 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" role="group">
          <button
            v-for="k in kindFilters"
            :key="k.value"
            :aria-pressed="filters.kind === k.value"
            class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-sm font-medium"
            :class="filters.kind === k.value ? 'border-transparent bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100' : 'border-surface-300 text-surface-900'"
            type="button"
            @click="setFilters({ kind: k.value })"
          >
            {{ k.label }}
            <span class="text-xs tabular-nums opacity-80">{{ counts[k.value] }}</span>
          </button>
        </div>

        <!-- From 768 px the list is here; on phones it is the view, under the pinned header -->
        <p v-if="mdAndUp && !loading && !loadError && shown.length === 0" class="m-0 px-2 text-sm text-surface-600">No models match.</p>

        <ul v-else-if="mdAndUp" aria-label="Sensor models" class="m-0 flex list-none flex-col gap-1 p-0">
          <ModelRow
            v-for="m in shown"
            :key="m.id"
            :active="m.id === modelId"
            :model="m"
            :to="{ name: 'sensors', params: { id: m.id }, query: listQuery }"
          />
        </ul>
      </div>
    </PaneContent>

    <FeedbackBanner v-if="loadError" type="error">{{ loadError }}</FeedbackBanner>

    <div v-else-if="loading" aria-label="Loading the catalogue…" class="flex flex-col gap-2" role="status">
      <v-skeleton-loader v-for="n in 4" :key="n" type="list-item-two-line" />
    </div>

    <!-- The view: one model -->
    <div v-else-if="selected" class="flex flex-col gap-8">
      <ModelGallery :can-write="canWrite" :model="selected" :refresh="photosVersion" @changed="loadModels" />

      <ModelSpecs :can-write="canWrite" :model="selected" @edit="editModel" />

      <ModelDocuments :can-write="canWrite" :model="selected" />

      <ModelUnits
        :can-write="canWrite"
        :error="unitsError"
        :focus="unitId"
        :model="selected"
        :units="units"
        @add="addUnit"
        @edit="editUnit"
      />
    </div>

    <!-- Phones: the list, which slides up under the pinned header's curve -->
    <template v-else-if="!mdAndUp && !modelId">
      <p v-if="shown.length === 0" class="m-0 py-8 text-center text-surface-600">No models match.</p>

      <ul v-else aria-label="Sensor models" class="m-0 flex list-none flex-col gap-1 p-0">
        <ModelRow
          v-for="m in shown"
          :key="m.id"
          :active="false"
          :model="m"
          :to="{ name: 'sensors', params: { id: m.id }, query: listQuery }"
        />
      </ul>
    </template>

    <!-- The view: nothing chosen yet (phones show the list alone) -->
    <div v-else-if="modelId" class="py-6">
      <FeedbackBanner type="info">That sensor model wasn’t found. Choose one from the list.</FeedbackBanner>
    </div>

    <div v-else class="flex flex-col items-center gap-2 py-14 text-center">
      <v-icon class="text-surface-500" :icon="icons.sensor" size="40" />
      <h2 class="m-0 text-h3 text-surface-900">Choose a sensor model</h2>
      <p class="m-0 max-w-sm text-sm text-surface-600">Its photos, specifications, datasheets and manuals, and every unit of it, are here.</p>
    </div>

    <ModelFormDialog
      v-if="canWrite"
      v-model="modelDialog"
      :model="editingModel"
      :suggestions="parameterSuggestions"
      @photos="onPhotosAdded"
      @reload="loadModels"
      @saved="onModelSaved"
    />

    <UnitFormDialog
      v-if="canWrite && selected"
      v-model="unitDialog"
      :model="selected"
      :unit="editingUnit"
      @reload="onUnitsChanged"
      @saved="onUnitsChanged"
    />
  </PageBody>
</template>

<script lang="ts" setup>
  import type { SensorFilters } from './sensors'
  import type { SensorModelOut, SensorUnitOut } from '@/api/models'
  import { mdiMagnify, mdiPencilOutline, mdiPlus } from '@mdi/js'
  import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { sensorModelsApi, sensorUnitsApi } from '@/api/operations'
  import { NetworkError } from '@/api/problem'
  import { usePaneSelection } from '@/app/shells/pane'
  import { icons } from '@/app/theme/icons'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import ParameterTags from '@/features/stations/ParameterTags.vue'
  import { kindLabel, sortParameters } from '@/features/stations/stations'
  import { useSessionStore } from '@/stores/session'
  import ModelDocuments from './ModelDocuments.vue'
  import ModelFormDialog from './ModelFormDialog.vue'
  import ModelGallery from './ModelGallery.vue'
  import ModelRow from './ModelRow.vue'
  import ModelSpecs from './ModelSpecs.vue'
  import ModelUnits from './ModelUnits.vue'
  import { forgetPhotoLinks } from './photoLinks'
  import { kindCounts, kindFilters, matchesModel, sensorFiltersFrom, sensorQueryFrom } from './sensors'
  import UnitFormDialog from './UnitFormDialog.vue'

  // /sensors and /sensors/:id (AFD §3; PRD CAL-1, DOC-1): the catalogue of models with their photos,
  // specifications, datasheets and manuals, and the units of each. Staff only. A few dozen models at
  // most, so the page loads them all once and filters here.
  const session = useSessionStore()
  const route = useRoute()
  const router = useRouter()
  const { mdAndUp } = useDisplay()

  const models = ref<SensorModelOut[]>([])
  const loading = ref(true)
  const loadError = ref<string | null>(null)
  const units = ref<SensorUnitOut[] | null>(null)
  const unitsError = ref<string | null>(null)
  /** Bumped when photos were added from the model form, so the gallery looks again. */
  const photosVersion = ref(0)

  const modelId = computed(() => typeof route.params.id === 'string' && route.params.id ? route.params.id : null)
  const unitId = computed(() => typeof route.query.unit === 'string' && route.query.unit ? route.query.unit : null)
  const open = computed(() => modelId.value !== null)
  usePaneSelection(() => open.value)

  const canWrite = computed(() => session.hasAnyRole(['technician', 'admin']))
  const filters = computed(() => sensorFiltersFrom(route.query))
  const listQuery = computed(() => sensorQueryFrom(filters.value))
  const shown = computed(() => models.value.filter(m => matchesModel(m, filters.value)))
  const counts = computed(() => kindCounts(models.value))
  const selected = computed(() => models.value.find(m => m.id === modelId.value) ?? null)
  const summary = computed(() => loading.value || loadError.value ? undefined : `${models.value.length} ${models.value.length === 1 ? 'model' : 'models'} in the catalogue`)

  function setFilters (patch: Partial<SensorFilters>): void {
    void router.replace({ query: { ...route.query, ...sensorQueryFrom({ ...filters.value, ...patch }) } })
  }

  async function loadModels (): Promise<void> {
    loadError.value = null
    try {
      models.value = (await sensorModelsApi.list()).items
    } catch (error) {
      // Keep what is on screen if we already had a catalogue: a missed refresh is not an error page
      if (models.value.length === 0) {
        loadError.value = error instanceof NetworkError
          ? 'This needs a connection. It will load when you have signal.'
          : 'We couldn’t load the catalogue. Reload the page to try again.'
      }
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

  // --- The forms (SEN-1, SEN-2) -----------------------------------------------------------------

  const modelDialog = ref(false)
  const editingModel = ref<SensorModelOut | null>(null)
  const unitDialog = ref(false)
  const editingUnit = ref<SensorUnitOut | null>(null)

  /** Codes the catalogue already uses, offered when a model's parameters are typed. */
  const parameterSuggestions = computed(() => sortParameters([...new Set(models.value.flatMap(m => m.parameters))]))

  function addModel (): void {
    editingModel.value = null
    modelDialog.value = true
  }

  function editModel (): void {
    editingModel.value = selected.value
    modelDialog.value = true
  }

  function onModelSaved (saved: SensorModelOut): void {
    const at = models.value.findIndex(m => m.id === saved.id)
    if (at === -1) {
      models.value = [...models.value, saved]
      void router.push({ name: 'sensors', params: { id: saved.id }, query: listQuery.value })
    } else {
      models.value = models.value.map(m => m.id === saved.id ? saved : m)
    }
  }

  /** Photos went up from the form: the gallery and the list's cover picture have changed. */
  async function onPhotosAdded (): Promise<void> {
    photosVersion.value++
    await loadModels()
  }

  function addUnit (): void {
    editingUnit.value = null
    unitDialog.value = true
  }

  function editUnit (unit: SensorUnitOut): void {
    editingUnit.value = unit
    unitDialog.value = true
  }

  /** Units changed: look at them again, and at the catalogue, whose rows count them. */
  async function onUnitsChanged (): Promise<void> {
    if (modelId.value) {
      await loadUnits(modelId.value)
    }
    await loadModels()
  }

  onMounted(() => {
    void loadModels()
  })
  // A ten-minute photo link must not outlive the page: the next person to sign in on this device
  // starts with none
  onBeforeUnmount(forgetPhotoLinks)
  watch(modelId, id => {
    if (id) {
      void loadUnits(id)
    } else {
      units.value = null
    }
  }, { immediate: true })
</script>
