<template>
  <PageBody bleed title="Map" wide>
    <!-- Phones: the filters open in a sheet, from a button over the map -->
    <template v-if="!mdAndUp" #actions>
      <v-btn :prepend-icon="mdiFilterVariant" variant="tonal" @click="sheet = true">
        Filters<span v-if="activeCount" class="ml-1 tabular-nums"><span class="sr-only">, </span>{{ activeCount }}<span class="sr-only"> active</span></span>
      </v-btn>
    </template>

    <!-- The pane: status, then the same filters as the list. They live in the address, so a map view can be shared. -->
    <!-- Phones: nothing in the pane but the tabs, which stay at the top with the header while the map scrolls under their curve -->
    <PaneContent :pin="!mdAndUp">
      <div v-if="mdAndUp" class="flex flex-col gap-4 px-3">
        <div aria-labelledby="map-status-h" class="flex flex-col gap-0.5" role="group">
          <h3 id="map-status-h" class="m-0 px-2 pb-1 text-sm font-semibold text-surface-900">Status</h3>

          <button
            v-for="option in statusOptions"
            :key="option.value"
            :aria-pressed="option.on"
            class="flex h-10 items-center gap-3 rounded-card px-3 text-left text-sm font-medium"
            :class="option.on ? 'bg-primary-50 text-primary-700 dark:text-primary' : 'text-surface-600 hover:bg-surface-100'"
            type="button"
            @click="toggleStatus(option.value)"
          >
            <StationStatusMark :status="option.value" />
            <span class="grow">{{ option.label }}</span>
            <span class="tabular-nums text-surface-600">{{ option.count }}</span>
          </button>
        </div>

        <StationFilterFields
          class="px-1"
          :facets="facets"
          :filters="filters"
          :show-org="isStaff"
          @change="setFilters"
        />

        <p class="m-0 px-2 text-sm text-surface-600">
          {{ shown.length }} of {{ stations.length }} stations shown.
          <button v-if="narrowed" class="font-medium text-primary hover:underline" type="button" @click="reset">Reset filters</button>
        </p>
      </div>
    </PaneContent>

    <!-- isolate: Leaflet's panes and controls have z-indexes of their own (up to 1000) and would draw over the pinned header's curve -->
    <div class="relative isolate flex size-full min-h-[70dvh] flex-col md:min-h-0">
      <FeedbackBanner v-if="loadError" class="m-3" type="error">{{ loadError }}</FeedbackBanner>

      <div v-else-if="directory.loading && !directory.loaded" aria-label="Loading the map…" class="grid grow place-items-center" role="status">
        <v-progress-circular color="primary" indeterminate />
      </div>

      <template v-else>
        <!-- Notes above the map; the map keeps the rest of the height -->
        <div v-if="!online || missingPosition > 0" class="flex flex-col gap-2 p-3 pb-0">
          <FeedbackBanner v-if="!online" type="warning">
            <strong>You’re offline.</strong> Map tiles you’ve already looked at still show. New areas stay blank, but the markers and the list work.
          </FeedbackBanner>

          <FeedbackBanner v-if="missingPosition > 0" type="info">
            {{ missingPosition }} {{ missingPosition === 1 ? 'station has' : 'stations have' }} no position yet and
            {{ missingPosition === 1 ? 'isn’t' : 'aren’t' }} on the map.
            <router-link class="font-medium text-current underline" :to="{ name: 'stations', query: listQuery }">Show them in the list</router-link>
          </FeedbackBanner>
        </div>

        <div class="relative min-h-0 grow">
          <MapView
            :empty-text="emptyText"
            :fit-key="fitKey"
            :stations="positioned"
            @open="open"
          />
        </div>
      </template>
    </div>

    <!-- Phones: the filters -->
    <v-bottom-sheet v-model="sheet" aria-labelledby="map-filters-h">
      <div class="flex flex-col gap-5 rounded-t-card bg-surface px-5 pb-[calc(20px+env(safe-area-inset-bottom))] pt-5">
        <div class="flex items-center justify-between">
          <h2 id="map-filters-h" class="m-0 text-h2 text-surface-900">Filters</h2>
          <v-btn class="text-primary" variant="text" @click="reset">Reset</v-btn>
        </div>

        <div aria-label="Status" class="flex flex-wrap gap-1.5" role="group">
          <button
            v-for="option in statusOptions"
            :key="option.value"
            :aria-pressed="option.on"
            class="inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-sm font-medium"
            :class="option.on ? 'border-transparent bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100' : 'border-surface-300 text-surface-700'"
            type="button"
            @click="toggleStatus(option.value)"
          >
            <StationStatusMark :status="option.value" />{{ option.label }}
          </button>
        </div>

        <StationFilterFields :facets="facets" :filters="filters" :show-org="isStaff" @change="setFilters" />

        <v-btn block color="primary" @click="sheet = false">Show {{ shown.length }} {{ shown.length === 1 ? 'station' : 'stations' }}</v-btn>
      </div>
    </v-bottom-sheet>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { StationStatus } from '@/api/models'
  import type { StationFilters } from '@/features/stations/stations'
  import { mdiFilterVariant } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, onMounted, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { NetworkError } from '@/api/problem'
  import { useOnline } from '@/app/composables/useOnline'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import StationStatusMark from '@/components/StationStatusMark.vue'
  import StationFilterFields from '@/features/stations/StationFilterFields.vue'
  import {
    extraFilterCount,
    facetsOf,
    filtersFrom,
    matchesOthers,
    queryFrom,
    STATUSES,
    statusLook,
  } from '@/features/stations/stations'
  import { useSessionStore } from '@/stores/session'
  import { useStationDirectory } from '@/stores/stationDirectory'
  import { hasPosition } from './map'
  import MapView from './MapView.vue'

  // /map (AFD §3; PRD MAP-1 to MAP-3). Clients see their own organization's stations: the server
  // scopes the list (rule 3). The filters are the list's, in the address; the status filter here
  // is a set (the map shows several statuses at once), written as `status=a,b`.
  const session = useSessionStore()
  const { isStaff } = storeToRefs(session)
  const route = useRoute()
  const router = useRouter()
  const { mdAndUp } = useDisplay()
  const online = useOnline()
  const directory = useStationDirectory()

  const sheet = ref(false)
  const stations = computed(() => directory.stations)

  const loadError = computed(() => {
    if (!directory.error || directory.loaded) {
      return null
    }
    return directory.error instanceof NetworkError
      ? 'This needs a connection. The map will load when you have signal.'
      : 'We couldn’t load the stations. Reload the page to try again.'
  })

  onMounted(() => {
    if (session.user) {
      void directory.load(session.user.id)
    }
  })

  // --- Filters (in the URL) ---------------------------------------------------------------------

  const ALL_STATUSES: readonly StationStatus[] = STATUSES
  /** The statuses on the map: all but decommissioned unless the address says otherwise (DBD). */
  const DEFAULT_ON: readonly StationStatus[] = ['operational', 'degraded', 'offline']

  const filters = computed(() => filtersFrom(route.query))
  const listQuery = computed(() => queryFrom(filters.value))
  const statusesOn = computed<readonly StationStatus[]>(() => {
    const raw = route.query.status
    const text = Array.isArray(raw) ? raw[0] : raw
    if (typeof text !== 'string' || !text) {
      return DEFAULT_ON
    }
    const chosen = text.split(',').filter((s): s is StationStatus => (ALL_STATUSES as readonly string[]).includes(s))
    return chosen.length > 0 ? chosen : DEFAULT_ON
  })

  const facets = computed(() => facetsOf(stations.value))
  const others = computed(() => stations.value.filter(s => matchesOthers(s, filters.value)))
  const shown = computed(() => others.value.filter(s => statusesOn.value.includes(s.status as StationStatus)))
  const positioned = computed(() => shown.value.filter(hasPosition))
  const missingPosition = computed(() => shown.value.length - positioned.value.length)
  const fitKey = computed(() => JSON.stringify([listQuery.value, statusesOn.value, directory.loaded]))

  const statusOptions = computed(() => STATUSES.map(value => ({
    value,
    label: statusLook[value].label,
    count: others.value.filter(s => s.status === value).length,
    on: statusesOn.value.includes(value),
  })))

  const activeCount = computed(() =>
    extraFilterCount(filters.value) + (filters.value.q ? 1 : 0) + (isDefaultStatuses() ? 0 : 1),
  )
  const narrowed = computed(() => activeCount.value > 0)

  function isDefaultStatuses (): boolean {
    return statusesOn.value.length === DEFAULT_ON.length && DEFAULT_ON.every(s => statusesOn.value.includes(s))
  }

  const emptyText = computed(() => {
    if (stations.value.length === 0) {
      return session.isClient ? 'Your organization has no stations here yet.' : 'No stations yet. They arrive with the station import.'
    }
    return shown.value.length === 0 ? 'No stations match these filters.' : 'None of these stations has a position yet.'
  })

  // The route updates when a navigation finishes: a second change made before then builds on the first
  let pending: Record<string, string | undefined> | null = null

  function replaceQuery (patch: Record<string, string | undefined>): void {
    const next = { ...(pending ?? route.query as Record<string, string | undefined>), ...patch }
    pending = next
    void router.replace({ query: next }).finally(() => {
      if (pending === next) {
        pending = null
      }
    })
  }

  function setFilters (patch: Partial<StationFilters>): void {
    const next = { ...filters.value, ...patch }
    const { status: _status, ...rest } = queryFrom(next)
    replaceQuery(rest)
  }

  function toggleStatus (status: StationStatus): void {
    const set = new Set(statusesOn.value)
    if (set.has(status)) {
      if (set.size === 1) {
        return // at least one status stays on
      }
      set.delete(status)
    } else {
      set.add(status)
    }
    const next = ALL_STATUSES.filter(s => set.has(s))
    const isDefault = next.length === DEFAULT_ON.length && DEFAULT_ON.every(s => set.has(s))
    replaceQuery({ status: isDefault ? undefined : next.join(',') })
  }

  function reset (): void {
    pending = {}
    void router.replace({ query: {} }).finally(() => {
      pending = null
    })
  }

  function open (id: string): void {
    void router.push({ name: 'stations', params: { id } })
  }
</script>
