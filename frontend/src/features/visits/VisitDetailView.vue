<template>
  <div class="flex flex-col gap-6">
    <FeedbackBanner v-if="visit.status === 'cancelled'" type="info">
      <p class="m-0 font-medium">This visit was cancelled.</p>
    </FeedbackBanner>

    <FeedbackBanner v-else-if="visit.status === 'ended' && visit.additional_visit_required" type="info">
      <p class="m-0 font-medium">Another visit is needed.</p>
      <p v-if="visit.follow_up_notes" class="m-0 mt-0.5 whitespace-pre-line">{{ visit.follow_up_notes }}</p>
    </FeedbackBanner>

    <dl class="m-0 grid min-w-0 grid-cols-[90px_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm sm:grid-cols-[110px_minmax(0,1fr)]">
      <dt class="text-surface-600">When</dt>
      <dd class="m-0 text-surface-900">{{ when }}<span v-if="zone" class="text-surface-600"> ({{ zoneName }} time)</span></dd>

      <dt class="text-surface-600">Lead</dt>
      <dd class="m-0 text-surface-900">{{ visit.lead.name }}</dd>

      <dt class="text-surface-600">Attending</dt>
      <dd class="m-0 text-surface-900">{{ names(visit.staff) }}</dd>

      <template v-if="visit.started_at">
        <dt class="text-surface-600">Started</dt>
        <dd class="m-0 text-surface-900">{{ formatWhen(visit.started_at, zone) }}</dd>
      </template>

      <template v-if="visit.ended_at">
        <dt class="text-surface-600">Ended</dt>
        <dd class="m-0 text-surface-900">{{ formatWhen(visit.ended_at, zone) }}</dd>
      </template>

      <dt class="text-surface-600">Request</dt>

      <dd class="m-0 min-w-0 text-surface-900">
        <router-link class="font-mono font-medium text-primary no-underline hover:underline" :to="{ name: 'requests', params: { id: visit.request_id } }" translate="no">{{ visit.request_ref }}</router-link>
        <span v-if="visit.request_title"> · {{ visit.request_title }}</span>
      </dd>
    </dl>

    <section aria-labelledby="vs-h" class="flex flex-col gap-2">
      <div class="flex items-baseline justify-between gap-3">
        <h2 id="vs-h" class="m-0 text-h3 text-surface-900">Stations</h2>
        <span class="text-sm text-surface-600">{{ visit.stations.length }} {{ visit.stations.length === 1 ? 'station' : 'stations' }}</span>
      </div>

      <!-- From 768 px: a table -->
      <div v-if="mdAndUp" class="overflow-x-auto">
        <table class="w-full border-collapse text-sm">
          <caption class="sr-only">Stations on this visit, with who owns each</caption>

          <thead>
            <tr class="bg-surface-100 text-left">
              <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Station</th>
              <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Owner</th>
              <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Times</th>
              <th class="px-3 py-3" scope="col"><span class="sr-only">Actions</span></th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="station in visit.stations" :key="station.station_id" class="border-t border-surface-200 align-top">
              <td class="px-3 py-3">
                <router-link class="font-medium text-surface-900 no-underline hover:underline" :to="{ name: 'stations', params: { id: station.station_id } }">{{ station.station_name }}</router-link>
                <div class="font-mono text-xs text-surface-600" translate="no">{{ station.station_code }}</div>
              </td>

              <td class="px-3 py-3 text-surface-900">{{ station.owner.name }}</td>
              <td class="px-3 py-3 text-surface-900">{{ stationTimes(visit, station) }}</td>

              <td class="px-3 py-2 text-right">
                <div class="flex flex-wrap items-center justify-end gap-2">
                  <span v-if="elsewhere(station)" class="text-left text-surface-600">{{ elsewhere(station) }}</span>

                  <v-btn
                    v-if="station.actions.includes('arrive')"
                    :loading="busy === `arrive-${station.station_id}`"
                    size="small"
                    variant="outlined"
                    @click="emit('arrive', station.station_id)"
                  >Arrive</v-btn>

                  <v-btn
                    v-if="station.actions.includes('depart')"
                    :loading="busy === `depart-${station.station_id}`"
                    size="small"
                    variant="outlined"
                    @click="emit('depart', station.station_id)"
                  >Depart</v-btn>

                  <v-btn
                    v-if="canChangeOwner"
                    class="text-primary"
                    size="small"
                    variant="text"
                    @click="emit('change-owner', station.station_id)"
                  >Change owner</v-btn>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Phones: a card for each station, its buttons as wide as the card -->
      <ul v-else aria-label="Stations" class="m-0 flex list-none flex-col gap-2 p-0">
        <li v-for="station in visit.stations" :key="station.station_id" class="flex flex-col items-stretch gap-1 rounded-card bg-surface-50 px-3.5 py-3">
          <span class="font-medium text-surface-900">{{ station.station_name }}</span>
          <span class="font-mono text-xs text-surface-600" translate="no">{{ station.station_code }}</span>
          <span class="text-sm text-surface-600">{{ ownedBy(station) }} · {{ stationTimes(visit, station) }}</span>
          <span v-if="elsewhere(station)" class="text-sm text-surface-600">{{ elsewhere(station) }}</span>

          <v-btn
            v-if="station.actions.includes('arrive')"
            block
            class="mt-2"
            :loading="busy === `arrive-${station.station_id}`"
            variant="outlined"
            @click="emit('arrive', station.station_id)"
          >Arrive</v-btn>

          <v-btn
            v-if="station.actions.includes('depart')"
            block
            class="mt-2"
            :loading="busy === `depart-${station.station_id}`"
            variant="outlined"
            @click="emit('depart', station.station_id)"
          >Depart</v-btn>

          <v-btn
            v-if="canChangeOwner"
            class="mt-1 self-start text-primary"
            size="small"
            variant="text"
            @click="emit('change-owner', station.station_id)"
          >Change owner</v-btn>
        </li>
      </ul>
    </section>

    <!-- Photos and video, for the people on the visit (clients see them from W12) -->
    <section v-if="showMedia" aria-labelledby="vm-h" class="flex flex-col gap-3">
      <div class="flex items-baseline justify-between gap-3">
        <h2 id="vm-h" class="m-0 text-h3 text-surface-900">Photos and video</h2>
        <span class="text-sm text-surface-600">{{ mediaCount }} {{ mediaCount === 1 ? 'file' : 'files' }}</span>
      </div>

      <p class="m-0 flex items-center gap-2 text-xs text-surface-700">
        <v-icon class="shrink-0 text-primary" :icon="mdiInformationOutline" size="16" />
        {{ visit.status === 'started'
          ? 'Photos and video are shared with the client when the visit ends. You can hide any of them first, or later.'
          : 'Photos and video are shared with the client. You can hide any of them from the menu on each one.' }}
      </p>

      <FeedbackBanner v-if="!online && pending.length > 0" :icon="mdiWifiOff" type="info">
        You’re offline. Uploads need a connection; they carry on when you have signal.
      </FeedbackBanner>

      <div class="flex flex-col">
        <StationMedia
          v-for="station in visit.stations"
          :key="station.station_id"
          :can-add="canAdd"
          class="border-t border-surface-200 py-4 first:border-t-0 first:pt-1"
          :is-admin="isAdmin"
          :me="me ?? ''"
          :pending="pending.filter(p => p.stationId === station.station_id)"
          :station="station"
          :visit-id="visit.id"
          @add="emit('add-media', station.station_id)"
          @changed="emit('changed', $event)"
          @discard="emit('discard-media', $event)"
          @retry="emit('retry-media', $event)"
        />
      </div>
    </section>

    <!-- The work record, read only: the owner fills it in on the phone (W12) -->
    <section v-if="showMedia && recorded.length > 0" aria-labelledby="wr-h" class="flex flex-col gap-3">
      <h2 id="wr-h" class="m-0 text-h3 text-surface-900">Work record</h2>

      <v-tabs
        v-if="recorded.length > 1"
        v-model="recordOf"
        aria-label="Station"
        color="primary"
        density="comfortable"
      >
        <v-tab v-for="station in recorded" :key="station.station_id" :value="station.station_id">
          <span class="flex flex-col items-start leading-tight">
            {{ station.station_name }}
            <small class="text-xs font-normal normal-case text-surface-600">Owner {{ station.owner.name }}</small>
          </span>
        </v-tab>
      </v-tabs>

      <p v-else-if="recorded[0]" class="m-0 text-sm text-surface-700">{{ recorded[0].station_name }} · Owner {{ recorded[0].owner.name }}</p>

      <WorkRecordView
        v-if="shownRecord?.work"
        :saved-by="shownRecord.work.updated_by === shownRecord.owner.id ? shownRecord.owner.name : null"
        :visit-ended="visit.status === 'ended'"
        :work="shownRecord.work"
        :zone="shownRecord.time_zone"
      />
    </section>

    <!-- Scheduling notes are staff only: the server leaves them out for a client -->
    <section v-if="visit.notes" aria-labelledby="vn-h" class="flex flex-col gap-2">
      <h2 id="vn-h" class="m-0 text-h3 text-surface-900">Notes</h2>
      <p class="m-0 whitespace-pre-line rounded-lg bg-surface-50 px-3.5 py-3 text-sm text-surface-900">{{ visit.notes }}</p>
    </section>
  </div>
</template>

<script lang="ts" setup>
  import type { VisitOut, VisitStation } from '@/api/models'
  import type { PendingMedia } from '@/app/composables/useVisitMedia'
  import { mdiInformationOutline, mdiWifiOff } from '@mdi/js'
  import { computed, ref, watch } from 'vue'
  import { useDisplay } from 'vuetify'
  import { useOnline } from '@/app/composables/useOnline'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { canAddMedia } from './media'
  import StationMedia from './StationMedia.vue'
  import { canDo, formatRange, formatWhen, names, stationTimes, visitZone, zoneLabel } from './visits'
  import WorkRecordView from './WorkRecordView.vue'

  // The body of /visits/:id (AFD J5, J6 step 3; DBD "Request page" layout). Dates are in the zone
  // of the first station; each station's own times are in its own zone. A client sees dates,
  // stations and names, no notes and no buttons. W12 moves Start, Arrive, Depart and End into the
  // field shell; the API and the rules stay.
  const props = defineProps<{
    visit: VisitOut
    isClient: boolean
    /** The action in progress (`start`, `arrive-<station>`, …), for its button's spinner. */
    busy?: string | null
    me?: string | null
    isAdmin?: boolean
    /** Files on their way to a station of this visit. */
    pending?: PendingMedia[]
  }>()

  const emit = defineEmits<{
    'arrive': [stationId: string]
    'depart': [stationId: string]
    'change-owner': [stationId: string]
    'add-media': [stationId: string]
    'retry-media': [key: string]
    'discard-media': [key: string]
    'changed': [visit: VisitOut]
  }>()

  const { mdAndUp } = useDisplay()
  const online = useOnline()
  const zone = computed(() => visitZone(props.visit))
  const zoneName = computed(() => zone.value ? zoneLabel(zone.value) : '')
  const when = computed(() => formatRange(props.visit.planned_start, props.visit.planned_end, zone.value))
  const canChangeOwner = computed(() => canDo(props.visit, 'change_owner') && ['planned', 'started'].includes(props.visit.status))

  // Media and the work record are for the people on the visit; a planned or cancelled visit has none
  const showMedia = computed(() => !props.isClient && (props.visit.status === 'started' || props.visit.status === 'ended'))
  const canAdd = computed(() => canAddMedia(props.visit, props.me ?? '', props.isAdmin ?? false))
  const mediaCount = computed(() => props.visit.stations.reduce((n, s) => n + s.media.length, 0))
  const pending = computed(() => props.pending ?? [])
  const recorded = computed(() => props.visit.stations.filter(s => s.work))
  const recordOf = ref<string | null>(null)
  const shownRecord = computed(() => recorded.value.find(s => s.station_id === recordOf.value) ?? recorded.value[0] ?? null)
  watch(recorded, list => {
    if (!list.some(s => s.station_id === recordOf.value)) {
      recordOf.value = list[0]?.station_id ?? null
    }
  }, { immediate: true })

  function ownedBy (station: VisitStation): string {
    return station.owner.id === props.me ? 'Owned by you' : `Owned by ${station.owner.name}`
  }

  /** Someone else's station on a started visit: read only, and it says whose it is (VIS-3). */
  function elsewhere (station: VisitStation): string {
    if (props.isClient || props.visit.status !== 'started' || station.actions.length > 0 || station.departed_at) {
      return ''
    }
    return `Owned by ${station.owner.name}. Only they can ${station.arrived_at ? 'depart' : 'arrive'} here.`
  }
</script>
