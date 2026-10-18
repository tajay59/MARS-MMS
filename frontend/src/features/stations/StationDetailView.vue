<template>
  <div class="flex flex-col">
    <!-- The tabs from DBD "Station page"; clients see fewer. The tab is in the URL (?tab=sensors). -->
    <v-tabs
      v-model="tab"
      class="-mx-4 -mt-4 border-b border-surface-200 md:-mx-8 md:-mt-7"
      color="primary"
      density="comfortable"
      show-arrows
    >
      <v-tab v-for="t in tabs" :key="t.key" class="px-4 md:first:ml-4" :value="t.key">
        {{ t.label }}
        <span v-if="t.count !== undefined" class="ml-1.5 rounded-full bg-surface-100 px-1.5 text-xs leading-5 text-surface-600 tabular-nums">{{ t.count }}</span>
      </v-tab>
    </v-tabs>

    <v-tabs-window v-model="tab" class="pt-6">
      <!-- Overview: the station's facts, its place and what needs calibrating -->
      <v-tabs-window-item value="overview">
        <div class="grid gap-8 lg:grid-cols-[minmax(0,1fr)_300px]">
          <dl class="m-0 grid grid-cols-[120px_minmax(0,1fr)] text-sm sm:grid-cols-[150px_minmax(0,1fr)]">
            <template v-for="(row, i) in facts" :key="row.label">
              <dt class="py-2.5 text-surface-600" :class="i > 0 ? 'border-t border-surface-200' : ''">{{ row.label }}</dt>

              <dd class="m-0 min-w-0 py-2.5 text-surface-900" :class="i > 0 ? 'border-t border-surface-200' : ''">
                <ParameterTags v-if="row.label === 'Measures' && station.parameters.length > 0" :parameters="station.parameters" />
                <span v-else class="wrap-break-word" :class="row.mono ? 'font-mono' : ''">{{ row.value }}</span>
              </dd>
            </template>
          </dl>

          <div class="flex flex-col gap-6">
            <!-- Where it is; the Map page draws it on a real map -->
            <div
              :aria-label="station.latitude !== null && station.longitude !== null ? `Location ${coordinates}` : 'No location recorded'"
              class="relative grid h-45 place-items-center rounded-card bg-surface-50"
              role="img"
            >
              <v-icon v-if="coordinates" :class="statusLook[status].mark" :icon="mdiMapMarker" size="36" />
              <span v-else class="text-sm text-surface-600">No location recorded</span>

              <span v-if="coordinates" class="absolute bottom-2 left-2.5 rounded-md bg-surface px-2 py-0.5 text-xs tabular-nums text-surface-700">
                {{ station.latitude?.toFixed(4) }}, {{ station.longitude?.toFixed(4) }}
              </span>
            </div>

            <section aria-labelledby="cal-h">
              <h2 id="cal-h" class="m-0 mb-1.5 text-h3 text-surface-900">Calibration</h2>
              <p v-if="units.length === 0" class="m-0 text-sm text-surface-600">No units installed.</p>

              <ul v-else class="m-0 flex list-none flex-col p-0 text-sm">
                <li v-for="unit in attention" :key="unit.unit_id" class="border-t border-surface-200 first:border-t-0">
                  <button class="flex w-full items-center justify-between gap-3 py-2.5 text-left hover:text-primary" type="button" @click="tab = 'sensors'">
                    <span class="min-w-0">{{ unit.model.manufacturer }} {{ unit.model.model }} · <span class="font-mono">{{ unit.parameter ?? kindLabel(unit.model.kind) }}</span></span>
                    <CalibrationDueChip :due="unit.calibration_due_at" :state="asDue(unit.due_state)" :time-zone="station.time_zone" />
                  </button>
                </li>

                <li class="border-t border-surface-200" :class="attention.length === 0 ? 'border-t-0' : ''">
                  <button class="flex w-full items-center justify-between gap-3 py-2.5 text-left text-surface-700 hover:text-primary" type="button" @click="tab = 'sensors'">
                    <span>{{ restSummary }}</span>
                    <v-icon :icon="mdiChevronRight" size="20" />
                  </button>
                </li>
              </ul>
            </section>
          </div>
        </div>
      </v-tabs-window-item>

      <!-- Sensors: what is installed now (CAL-3) -->
      <v-tabs-window-item value="sensors">
        <p v-if="units.length === 0" class="m-0 py-8 text-center text-surface-600">No units are installed at this station.</p>

        <div v-else-if="mdAndUp" class="overflow-x-auto">
          <table class="w-full border-collapse text-sm">
            <caption class="sr-only">Units installed at {{ station.name }}</caption>

            <thead>
              <tr class="bg-surface-100 text-left">
                <th v-for="h in ['Measures', 'Model', 'Serial', 'Installed', 'Last calibrated', 'Calibration']" :key="h" class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">{{ h }}</th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="unit in units" :key="unit.unit_id" class="h-13 border-t border-surface-200">
                <td class="whitespace-nowrap px-4" :class="unit.parameter ? 'font-mono text-surface-900' : 'text-surface-600'">{{ unit.parameter ?? kindLabel(unit.model.kind) }}</td>
                <td class="px-4 text-surface-900">{{ unit.model.manufacturer }} {{ unit.model.model }}</td>

                <td class="whitespace-nowrap px-4 font-mono text-surface-900">
                  {{ unit.serial }}
                  <v-icon
                    v-if="isStaff && unit.needs_review"
                    aria-hidden="false"
                    aria-label="Flagged for review"
                    class="ml-1 text-on-warning-container"
                    :icon="mdiFlagOutline"
                    size="16"
                  />
                </td>

                <td class="whitespace-nowrap px-4 tabular-nums text-surface-900">{{ formatDate(unit.installed_at, station.time_zone) }}</td>

                <td class="whitespace-nowrap px-4 tabular-nums" :class="unit.last_calibrated_at ? 'text-surface-900' : 'text-surface-600'">
                  {{ unit.last_calibrated_at ? formatDate(unit.last_calibrated_at, station.time_zone) : 'Not calibrated' }}
                </td>

                <td class="px-4"><CalibrationDueChip :due="unit.calibration_due_at" :state="asDue(unit.due_state)" :time-zone="station.time_zone" /></td>
              </tr>
            </tbody>
          </table>
        </div>

        <ul v-else :aria-label="`Units installed at ${station.name}`" class="m-0 flex list-none flex-col p-0">
          <li v-for="unit in units" :key="unit.unit_id" class="flex flex-col gap-1 border-t border-surface-200 py-3 first:border-t-0">
            <span class="flex items-start justify-between gap-2">
              <span class="font-medium text-surface-900">
                <span :class="unit.parameter ? 'font-mono' : ''">{{ unit.parameter ?? kindLabel(unit.model.kind) }}</span> · {{ unit.model.manufacturer }} {{ unit.model.model }}
              </span>

              <CalibrationDueChip :due="unit.calibration_due_at" :state="asDue(unit.due_state)" :time-zone="station.time_zone" />
            </span>

            <span class="text-sm text-surface-600">
              <span class="font-mono">{{ unit.serial }}</span>
              · {{ unit.last_calibrated_at ? `Calibrated ${formatDate(unit.last_calibrated_at, station.time_zone)}` : 'Not calibrated' }}
            </span>
          </li>
        </ul>
      </v-tabs-window-item>

      <!-- Calibration: the records made at this station, newest first (staff) -->
      <v-tabs-window-item v-if="isStaff" value="calibration">
        <FeedbackBanner v-if="calError" type="error">{{ calError }}</FeedbackBanner>

        <div v-else-if="calibrations === null" aria-label="Loading calibrations…" role="status">
          <v-skeleton-loader v-for="n in 3" :key="n" type="list-item-two-line" />
        </div>

        <p v-else-if="calibrations.length === 0" class="m-0 py-8 text-center text-surface-600">No calibrations recorded at this station yet.</p>

        <div v-else class="flex flex-col gap-3">
          <div class="overflow-x-auto">
            <table class="w-full border-collapse text-sm">
              <caption class="sr-only">Calibrations at {{ station.name }}, newest first</caption>

              <thead>
                <tr class="bg-surface-100 text-left">
                  <th v-for="h in ['Date', 'Unit', 'Method', 'Result', 'Performed by']" :key="h" class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">{{ h }}</th>
                </tr>
              </thead>

              <tbody>
                <tr v-for="c in calibrations" :key="c.id" class="h-13 border-t border-surface-200">
                  <td class="whitespace-nowrap px-4 tabular-nums text-surface-900">{{ formatDate(c.at, station.time_zone) }}</td>

                  <td class="px-4 text-surface-900">
                    <template v-if="unitNames.get(c.sensor_unit_id)">
                      {{ unitNames.get(c.sensor_unit_id)!.model }} · <span class="font-mono">{{ unitNames.get(c.sensor_unit_id)!.serial }}</span>
                    </template>

                    <span v-else class="text-surface-600">A unit since moved</span>
                  </td>

                  <td class="whitespace-nowrap px-4 text-surface-900">{{ methodLabel[c.method] ?? c.method }}</td>

                  <td class="px-4">
                    <span class="inline-flex h-6 items-center rounded-full px-2.5 text-xs font-medium" :class="(resultLook[c.result] ?? resultLook.pass!).chip">
                      {{ resultLook[c.result]?.label ?? c.result }}
                    </span>
                  </td>

                  <td class="px-4 text-surface-900">{{ c.performed_by ?? '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <v-btn
            v-if="calNext"
            class="self-start text-primary"
            :loading="calLoading"
            variant="text"
            @click="loadCalibrations(true)"
          >Show older</v-btn>
        </div>
      </v-tabs-window-item>

      <!-- Tabs whose data arrives in later phases keep their place (approved mock-up) -->
      <v-tabs-window-item v-for="t in laterTabs" :key="t.key" :value="t.key">
        <div class="flex flex-col items-center gap-2 py-14 text-center">
          <v-icon class="text-surface-500" :icon="mdiProgressClock" size="40" />
          <h2 class="m-0 text-h3 text-surface-900">{{ t.label }} aren’t built yet</h2>
          <p class="m-0 max-w-sm text-sm text-surface-600">They arrive in phase {{ t.phase }} of the plan.</p>
        </div>
      </v-tabs-window-item>
    </v-tabs-window>
  </div>
</template>

<script lang="ts" setup>
  import type { DueState } from './stations'
  import type { CalibrationOut, StationDetail } from '@/api/models'
  import { mdiChevronRight, mdiFlagOutline, mdiMapMarker, mdiProgressClock } from '@mdi/js'
  import { computed, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { calibrationsApi, sensorUnitsApi } from '@/api/operations'
  import { NetworkError } from '@/api/problem'
  import { formatCoordinates, formatDate, formatPlainDate } from '@/app/format'
  import CalibrationDueChip from '@/components/CalibrationDueChip.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import ParameterTags from './ParameterTags.vue'
  import { isStatus, kindLabel, methodLabel, resultLook, sortInstalled, statusLook } from './stations'

  // The body of /stations/:id (DBD "Station page"). Clients see a summary: no configurations,
  // calibration records or history, and the server leaves out the QR token (rule 6).
  const props = defineProps<{ station: StationDetail, isStaff: boolean }>()

  const route = useRoute()
  const router = useRouter()
  const { mdAndUp } = useDisplay()

  interface Tab { key: string, label: string, staff?: boolean, phase?: number, count?: number }

  const tabs = computed<Tab[]>(() => ([
    { key: 'overview', label: 'Overview' },
    { key: 'sensors', label: 'Sensors', count: props.station.installed.length },
    { key: 'documents', label: 'Documents', phase: 2 },
    { key: 'configurations', label: 'Configurations', staff: true, phase: 2 },
    { key: 'requests', label: 'Requests', phase: 3 },
    { key: 'visits', label: 'Visits', phase: 4 },
    { key: 'reports', label: 'Reports', phase: 6 },
    { key: 'calibration', label: 'Calibration', staff: true },
    { key: 'history', label: 'History', staff: true, phase: 7 },
  ] as Tab[]).filter(t => props.isStaff || !t.staff))
  const laterTabs = computed(() => tabs.value.filter(t => t.phase !== undefined))

  const tab = computed<string>({
    get: () => {
      const value = route.query.tab
      return typeof value === 'string' && tabs.value.some(t => t.key === value) ? value : 'overview'
    },
    set: value => {
      void router.replace({ query: { ...route.query, tab: value === 'overview' ? undefined : value } })
    },
  })

  const status = computed(() => isStatus(props.station.status) ? props.station.status : 'decommissioned')
  const units = computed(() => sortInstalled(props.station.installed))
  const attention = computed(() => units.value.filter(u => u.due_state === 'overdue' || u.due_state === 'due_soon'))
  const restSummary = computed(() => {
    const ok = units.value.filter(u => u.due_state === 'ok').length
    const none = units.value.filter(u => !u.due_state).length
    const parts = [`${ok} in date`]
    if (none > 0) {
      parts.push(`${none} with no interval`)
    }
    return parts.join(' · ')
  })

  function asDue (value: string | null): DueState | null {
    return (['overdue', 'due_soon', 'ok'] as const).find(state => state === value) ?? null
  }

  const coordinates = computed(() => {
    const { latitude, longitude } = props.station
    return latitude === null || longitude === null ? '' : formatCoordinates(latitude, longitude)
  })

  const facts = computed(() => {
    const s = props.station
    const join = (...parts: (string | null | undefined)[]) => parts.filter(Boolean).join(' · ') || '—'
    const logger = s.logger as { model?: string | null, serial?: string | null, firmware?: string | null } | null
    const comms = s.comms as { type?: string | null, provider?: string | null, identifier?: string | null } | null
    const power = s.power as { panel_w?: number | null, battery_ah?: number | null, controller?: string | null } | null
    const rows: { label: string, value: string, mono?: boolean }[] = [
      { label: 'Type', value: s.type ?? '—' },
      { label: 'Region', value: s.region ?? '—' },
      {
        label: 'Location',
        value: coordinates.value
          ? join(coordinates.value, s.elevation_m === null ? null : `${s.elevation_m} m`)
          : '—',
      },
      { label: 'Time zone', value: s.time_zone },
      { label: 'Installed', value: formatPlainDate(s.install_date) },
      { label: 'Measures', value: s.parameters.length > 0 ? '' : '—' },
      { label: 'Logger', value: join(logger?.model, logger?.serial, logger?.firmware && `firmware ${logger.firmware}`) },
      { label: 'Communications', value: join(comms?.type, comms?.provider, props.isStaff ? comms?.identifier : null) },
      {
        label: 'Power',
        value: join(
          power?.panel_w ? `${power.panel_w} W panel` : null,
          power?.battery_ah ? `${power.battery_ah} Ah battery` : null,
          power?.controller,
        ),
      },
      { label: 'Access', value: s.access_notes ?? '—' },
    ]
    return rows
  })

  // --- Calibration records (staff), loaded when the tab first opens ----------------------------

  const calibrations = ref<CalibrationOut[] | null>(null)
  const calNext = ref<string | null>(null)
  const calLoading = ref(false)
  const calError = ref<string | null>(null)
  const unitNames = ref(new Map<string, { model: string, serial: string }>())

  async function loadCalibrations (more = false): Promise<void> {
    calLoading.value = true
    calError.value = null
    try {
      const page = await calibrationsApi.list({ station_id: props.station.id, after: more ? calNext.value ?? undefined : undefined, limit: 100 })
      calibrations.value = more ? [...(calibrations.value ?? []), ...page.items] : page.items
      calNext.value = page.next_after
      await nameUnits(page.items)
    } catch (error) {
      calError.value = error instanceof NetworkError
        ? 'This needs a connection. It will load when you have signal.'
        : 'We couldn’t load the calibrations. Reload the page to try again.'
    } finally {
      calLoading.value = false
    }
  }

  /** Units installed here are named from the station; one moved away since is looked up. */
  async function nameUnits (records: CalibrationOut[]): Promise<void> {
    const names = new Map(unitNames.value)
    for (const u of props.station.installed) {
      names.set(u.unit_id, { model: `${u.model.manufacturer} ${u.model.model}`, serial: u.serial })
    }
    const missing = [...new Set(records.map(r => r.sensor_unit_id))].filter(id => !names.has(id))
    const found = await Promise.allSettled(missing.map(id => sensorUnitsApi.get(id)))
    for (const result of found) {
      if (result.status === 'fulfilled') {
        const u = result.value
        names.set(u.id, { model: `${u.model.manufacturer} ${u.model.model}`, serial: u.serial })
      }
    }
    unitNames.value = names
  }

  watch([tab, () => props.station.id], ([value, id], [, before]) => {
    if (id !== before) {
      calibrations.value = null
      calNext.value = null
      calError.value = null
    }
    if (value === 'calibration' && props.isStaff && calibrations.value === null && !calLoading.value) {
      void loadCalibrations()
    }
  }, { immediate: true })
</script>
