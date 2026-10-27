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

    <PreparePanel :key="visit.id" :visit="visit" />

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

    <!-- Each station's board (W11-18): staff from the start, a client the shared part after the end -->
    <VisitBoard v-if="showBoards" :is-client="isClient" :me="me" :visit="visit" />

    <!-- The draft report, once the end has synced (W16): staff only -->
    <ReportSection
      v-if="!isClient && visit.status === 'ended'"
      ended
      :may-draw="mayDraw"
      :visit-id="visit.id"
      :zone="zone"
    />

    <!-- Scheduling notes are staff only: the server leaves them out for a client -->
    <section v-if="visit.notes" aria-labelledby="vn-h" class="flex flex-col gap-2">
      <h2 id="vn-h" class="m-0 text-h3 text-surface-900">Notes</h2>
      <p class="m-0 whitespace-pre-line rounded-lg bg-surface-50 px-3.5 py-3 text-sm text-surface-900">{{ visit.notes }}</p>
    </section>
  </div>
</template>

<script lang="ts" setup>
  import type { VisitOut, VisitStation } from '@/api/models'
  import { computed } from 'vue'
  import { useDisplay } from 'vuetify'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import VisitBoard from './board/VisitBoard.vue'
  import PreparePanel from './prepare/PreparePanel.vue'
  import ReportSection from './report/ReportSection.vue'
  import { canDo, formatRange, formatWhen, names, stationTimes, visitZone, zoneLabel } from './visits'

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
  }>()

  const emit = defineEmits<{
    'arrive': [stationId: string]
    'depart': [stationId: string]
    'change-owner': [stationId: string]
  }>()

  const { mdAndUp } = useDisplay()
  const zone = computed(() => visitZone(props.visit))
  const zoneName = computed(() => zone.value ? zoneLabel(zone.value) : '')
  const when = computed(() => formatRange(props.visit.planned_start, props.visit.planned_end, zone.value))
  // Attending staff and admins draw the preview; a viewer reads (W16-12)
  const mayDraw = computed(() => !!props.isAdmin || props.visit.lead.id === props.me || props.visit.staff.some(person => person.id === props.me))
  const canChangeOwner = computed(() => canDo(props.visit, 'change_owner') && ['planned', 'started'].includes(props.visit.status))

  // The boards fill in once the visit has started; a client sees them once it has ended (W11-28)
  const showBoards = computed(() => props.isClient
    ? props.visit.status === 'ended'
    : props.visit.status === 'started' || props.visit.status === 'ended')

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
