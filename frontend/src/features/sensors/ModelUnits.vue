<template>
  <section aria-labelledby="units-h">
    <div class="mb-2.5 flex flex-wrap items-center justify-between gap-2">
      <h2 id="units-h" class="m-0 flex items-center gap-2 text-h3 text-surface-900">
        Units of this model
        <span v-if="units" class="rounded-full bg-surface-100 px-2 text-sm font-medium text-surface-800">{{ units.length }}</span>
      </h2>

      <v-btn
        v-if="canWrite"
        color="primary"
        :prepend-icon="mdiPlus"
        variant="tonal"
        @click="$emit('add')"
      >Add a unit</v-btn>
    </div>

    <FeedbackBanner v-if="error" type="error">{{ error }}</FeedbackBanner>

    <div v-else-if="units === null" aria-label="Loading units…" role="status">
      <v-skeleton-loader type="list-item-two-line" />
    </div>

    <p v-else-if="units.length === 0" class="m-0 py-4 text-sm text-surface-600">No units of this model are registered yet.</p>

    <div v-else class="flex flex-col gap-4">
      <!-- Tablet and desktop: a table, one row a unit -->
      <div v-if="mdAndUp" class="overflow-x-auto">
        <table class="w-full border-collapse text-sm">
          <caption class="sr-only">Units of {{ model.manufacturer }} {{ model.model }}</caption>

          <thead>
            <tr class="bg-surface-100 text-left">
              <th v-for="h in ['Serial', 'Status', 'Where', 'Calibration']" :key="h" class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">{{ h }}</th>
              <th v-if="canWrite" class="w-14 px-2 py-3" scope="col"><span class="sr-only">Actions</span></th>
            </tr>
          </thead>

          <tbody>
            <tr
              v-for="u in units"
              :key="u.id"
              class="h-13 border-t border-surface-200 transition-colors"
              :class="u.id === shown?.id ? 'bg-primary-50' : 'hover:bg-surface-50'"
            >
              <td class="whitespace-nowrap px-4 font-mono text-surface-900" translate="no">
                <button
                  :aria-label="`Show the calibration of ${u.serial}`"
                  :aria-pressed="u.id === shown?.id"
                  class="cursor-pointer border-0 bg-transparent p-0 font-mono text-surface-900 hover:underline"
                  type="button"
                  @click="picked = u.id"
                >{{ u.serial }}</button>

              </td>

              <td class="whitespace-nowrap px-4"><UnitStatusChip :status="u.status" /></td>

              <td class="px-4 text-surface-900">
                <span class="inline-flex items-center gap-1.5">
                  <v-icon class="shrink-0 text-surface-500" :icon="whereIcon(u.status)" size="18" />
                  <router-link v-if="u.station" class="text-primary no-underline hover:underline" :to="stationLink(u)">{{ whereLabel(u) }}</router-link>
                  <template v-else>{{ whereLabel(u) }}</template>
                </span>
              </td>

              <td class="px-4"><CalibrationDueChip :due="u.calibration_due_at" :state="asDue(u.due_state)" /></td>

              <td v-if="canWrite" class="px-2 text-right">
                <UnitMenu :unit="u" @edit="$emit('edit', u)" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Phones: a card each, with its calibration along the foot -->
      <ul v-else aria-label="Units" class="m-0 flex list-none flex-col gap-2 p-0">
        <li v-for="u in units" :key="u.id" class="flex flex-col overflow-hidden rounded-card bg-surface-50">
          <div class="flex flex-col gap-2 px-3.5 pb-2.5 pt-3">
            <div class="flex items-center justify-between gap-2">
              <div class="flex min-w-0 flex-wrap items-center gap-2">
                <span class="font-mono font-semibold text-surface-900" translate="no">{{ u.serial }}</span>
                <UnitStatusChip :status="u.status" />
              </div>

              <UnitMenu v-if="canWrite" :unit="u" @edit="$emit('edit', u)" />
            </div>

            <div class="flex items-center gap-1.5 text-sm text-surface-800">
              <v-icon class="shrink-0 text-surface-500" :icon="whereIcon(u.status)" size="18" />
              <router-link v-if="u.station" class="truncate text-primary no-underline" :to="stationLink(u)">{{ whereLabel(u) }}</router-link>
              <span v-else class="truncate">{{ whereLabel(u) }}</span>
            </div>
          </div>

          <div class="flex items-center justify-between gap-2 bg-surface-100 px-3.5 py-2">
            <CalibrationDueChip :due="u.calibration_due_at" :state="asDue(u.due_state)" />
            <span v-if="u.last_calibrated_at" class="truncate text-xs text-surface-600">Last: {{ formatDate(u.last_calibrated_at) }}</span>
          </div>
        </li>
      </ul>

      <!-- The calibration of the unit picked above (or the first that needs attention) -->
      <div v-if="mdAndUp && shown" class="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 rounded-card bg-surface-50 px-4 py-3" role="status">
        <div class="flex min-w-0 flex-col gap-0.5">
          <div class="flex flex-wrap items-center gap-2">
            <span class="font-semibold text-surface-900">Calibration of <span class="font-mono" translate="no">{{ shown.serial }}</span></span>
            <CalibrationDueChip :due="shown.calibration_due_at" :state="asDue(shown.due_state)" />
          </div>

          <span class="text-sm text-surface-700">{{ calibrationSentence(shown) }}</span>
        </div>

        <router-link v-if="shown.station" class="inline-flex items-center gap-1 text-sm text-primary no-underline hover:underline" :to="stationLink(shown)">
          Open at {{ shown.station.name }}<v-icon :icon="mdiChevronRight" size="18" />
        </router-link>
      </div>

      <!-- How many are within calibration -->
      <div v-if="fitness" class="rounded-card bg-primary-50 px-4 py-3">
        <div class="flex items-center justify-between gap-2 text-sm">
          <span class="font-medium text-surface-900">Within calibration</span>
          <span class="font-semibold tabular-nums text-primary">{{ fitness.percent }}%</span>
        </div>

        <div
          :aria-label="`${fitness.ok} of ${fitness.of} units within calibration`"
          aria-valuemax="100"
          aria-valuemin="0"
          :aria-valuenow="fitness.percent"
          class="my-2 h-2 overflow-hidden rounded-full bg-surface-200"
          role="progressbar"
        >
          <div class="h-full rounded-full bg-primary" :style="{ width: `${fitness.percent}%` }" />
        </div>

        <p class="m-0 text-xs text-surface-700">{{ fitness.ok }} of {{ fitness.of }} {{ fitness.of === 1 ? 'unit has' : 'units have' }} a calibration that is in date or due within 30 days.</p>
      </div>
    </div>
  </section>
</template>

<script lang="ts" setup>
  import type { SensorModelOut, SensorUnitOut } from '@/api/models'
  import type { DueState } from '@/features/stations/stations'
  import { mdiChevronRight, mdiPlus } from '@mdi/js'
  import { computed, ref, watch } from 'vue'
  import { useDisplay } from 'vuetify'
  import { formatDate } from '@/app/format'
  import CalibrationDueChip from '@/components/CalibrationDueChip.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { calibrationSentence, compliance, firstToShow, whereIcon, whereLabel } from './sensors'
  import UnitMenu from './UnitMenu.vue'
  import UnitStatusChip from './UnitStatusChip.vue'

  // The units of one sensor model: where each is, its state and its calibration. A table on a
  // tablet or desktop, cards on a phone. Whoever may write also gets the add and edit actions.
  const props = defineProps<{
    model: SensorModelOut
    units: SensorUnitOut[] | null
    error: string | null
    canWrite: boolean
    /** A unit to show first (`?unit=` in the address). */
    focus?: string | null
  }>()

  defineEmits<{
    add: []
    edit: [unit: SensorUnitOut]
  }>()

  const { mdAndUp } = useDisplay()
  const picked = ref<string | null>(null)

  watch(() => props.focus, id => {
    if (id) {
      picked.value = id
    }
  }, { immediate: true })

  const shown = computed(() => {
    const list = props.units ?? []
    return list.find(u => u.id === picked.value) ?? firstToShow(list)
  })
  const fitness = computed(() => compliance(props.units ?? []))

  function asDue (value: string | null): DueState | null {
    return (['overdue', 'due_soon', 'ok'] as const).find(state => state === value) ?? null
  }

  function stationLink (unit: SensorUnitOut) {
    return { name: 'stations', params: { id: unit.station?.id }, query: { tab: 'sensors' } }
  }
</script>
