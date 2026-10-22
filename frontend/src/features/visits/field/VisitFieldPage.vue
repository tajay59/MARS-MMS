<template>
  <PageBody>
    <div class="flex grow flex-col">
      <div v-if="detailError" class="px-4 pt-4">
        <FeedbackBanner :type="detailError === 'missing' ? 'info' : 'error'">{{ detailMessage }}</FeedbackBanner>
      </div>

      <div v-else-if="!detail" aria-label="Loading the visit…" class="flex flex-col gap-3 px-4 pt-4" role="status">
        <v-skeleton-loader type="heading, list-item-two-line, list-item-two-line" />
      </div>

      <!-- One station: its facts, Arrive or Depart, and its board -->
      <div v-else-if="current" class="flex flex-col gap-4 px-4 pb-6 pt-4">
        <section aria-labelledby="vf-station-h" class="flex flex-col gap-1">
          <h2 id="vf-station-h" class="m-0 text-h3 text-surface-900">{{ current.station_name }}</h2>
          <span class="font-mono text-xs text-surface-600" translate="no">{{ current.station_code }}</span>
          <span class="text-sm text-surface-600">{{ ownedBy(current) }} · {{ stationTimes(detail, current) }}</span>

          <p v-if="current.owner.id !== me" class="m-0 mt-1 text-sm text-surface-900">
            Owned by {{ current.owner.name }}. You can add your own notes, tasks and files.
          </p>

          <v-btn
            v-if="current.actions.includes('arrive')"
            block
            class="mt-2"
            color="primary"
            :loading="busy === `arrive-${current.station_id}`"
            @click="arrive(current.station_id)"
          >Arrive</v-btn>

          <v-btn
            v-if="current.actions.includes('depart')"
            block
            class="mt-2"
            color="primary"
            :loading="busy === `depart-${current.station_id}`"
            variant="outlined"
            @click="depart(current.station_id)"
          >Depart</v-btn>
        </section>

        <VisitBoard field :is-client="false" :me="me" :visit="detail" />
      </div>

      <!-- The stations on the visit -->
      <template v-else>
        <div class="flex flex-col gap-4 px-4 pb-6 pt-4">
          <section aria-label="This visit" class="flex flex-col gap-1.5">
            <div class="flex items-center gap-2">
              <VisitStatusChip :status="detail.status" />

              <router-link
                v-if="detail.request_ref"
                class="font-mono text-xs font-medium text-surface-900"
                :to="{ name: 'requests', params: { id: detail.request_id } }"
                translate="no"
              >{{ detail.request_ref }}</router-link>
            </div>

            <p v-if="detail.request_title" class="m-0 font-medium text-surface-900">{{ detail.request_title }}</p>
            <p class="m-0 text-sm text-surface-600">{{ formatRange(detail.planned_start, detail.planned_end, zone) }}</p>
          </section>

          <section aria-labelledby="vf-stations-h" class="flex flex-col gap-2">
            <h2 id="vf-stations-h" class="m-0 text-h3 text-surface-900">Stations</h2>

            <ul aria-label="Stations" class="m-0 flex list-none flex-col gap-2 p-0">
              <li v-for="station in detail.stations" :key="station.station_id" class="flex flex-col rounded-card bg-surface-50">
                <router-link
                  class="flex min-h-16 flex-col gap-0.5 rounded-card px-3.5 py-3 text-surface-900 no-underline active:bg-surface-100"
                  :to="{ name: 'visit-field', params: { id: detail.id }, query: { station: station.station_id } }"
                >
                  <span class="font-medium">{{ station.station_name }}</span>
                  <span class="font-mono text-xs text-surface-600" translate="no">{{ station.station_code }}</span>
                  <span class="text-sm text-surface-600">{{ ownedBy(station) }} · {{ stationTimes(detail, station) }}</span>
                  <span class="text-sm text-surface-900">{{ summaryText(station.board) }}</span>
                </router-link>

                <div v-if="station.actions.length > 0" class="px-3.5 pb-3">
                  <v-btn
                    v-if="station.actions.includes('arrive')"
                    block
                    color="primary"
                    :loading="busy === `arrive-${station.station_id}`"
                    @click="arrive(station.station_id)"
                  >Arrive</v-btn>

                  <v-btn
                    v-if="station.actions.includes('depart')"
                    block
                    color="primary"
                    :loading="busy === `depart-${station.station_id}`"
                    variant="outlined"
                    @click="depart(station.station_id)"
                  >Depart</v-btn>
                </div>
              </li>
            </ul>
          </section>
        </div>

        <!-- Sticky action bar above the bottom navigation (DBD field shell) -->
        <div v-if="canDo(detail, 'end')" class="sticky bottom-0 mt-auto bg-surface px-4 py-3 shadow-[0_-8px_24px_rgb(15_23_42/0.12)]">
          <v-btn block color="primary" :height="48" @click="endOpen = true">End visit</v-btn>
        </div>
      </template>
    </div>

    <EndVisitDialog
      v-if="detail"
      v-model="endOpen"
      :visit="detail"
      @changed="reload"
      @done="ended"
    />

    <v-snackbar v-model="toast.show" location="top" :timeout="6000">{{ toast.text }}</v-snackbar>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { VisitOut, VisitStation } from '@/api/models'
  import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { visitsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { isVisitUpdate, settled, useLive } from '@/app/composables/useLive'
  import { useFieldBar } from '@/app/shells/fieldBar'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import VisitStatusChip from '@/components/VisitStatusChip.vue'
  import { useSessionStore } from '@/stores/session'
  import { summaryText } from '../board'
  import VisitBoard from '../board/VisitBoard.vue'
  import EndVisitDialog from '../EndVisitDialog.vue'
  import { forgetMediaLinks } from '../mediaLinks'
  import { useVisitMoves } from '../useVisitMoves'
  import { canDo, formatRange, stationTimes, visitZone } from '../visits'

  // /visits/:id/field (AFD J6 steps 2 to 9; DBD "Field"; W12): a started visit on a phone. The list
  // of its stations, each with Arrive or Depart for the ones this person owns; a station opens its
  // board (`?station=`). The rules and the buttons come from the server (`actions`); this page only
  // lays them out. Phones are sent here from /visits/:id; any other screen, or a visit that is no
  // longer started, goes back to the visit page.
  const route = useRoute()
  const router = useRouter()
  const session = useSessionStore()
  const { mdAndUp } = useDisplay()

  const me = computed(() => session.user?.id ?? null)
  const visitId = computed(() => String(route.params.id))
  const detail = ref<VisitOut | null>(null)
  const detailError = ref<'missing' | 'offline' | 'failed' | null>(null)
  const detailMessage = computed(() => {
    switch (detailError.value) {
      case 'missing': {
        return 'We can’t find this visit. It may have been removed, or the link may be wrong.'
      }
      case 'offline': {
        return 'This needs a connection. It will load when you have signal.'
      }
      default: {
        return 'We couldn’t load this visit. Reload the page to try again.'
      }
    }
  })
  const toast = reactive({ show: false, text: '' })
  const endOpen = ref(false)
  let leaving = false

  const zone = computed(() => detail.value ? visitZone(detail.value) : null)
  const current = computed<VisitStation | null>(() => {
    const wanted = route.query.station
    return typeof wanted === 'string' ? detail.value?.stations.find(s => s.station_id === wanted) ?? null : null
  })

  useFieldBar(() => current.value
    ? { title: current.value.station_name ?? 'Station', back: { name: 'visit-field', params: { id: visitId.value } }, backLabel: 'Back to the stations' }
    : { title: detail.value?.ref ?? 'Visit', back: { name: 'visits' }, backLabel: 'Back to visits' })

  function say (text: string): void {
    toast.text = text
    toast.show = true
  }

  function ownedBy (station: VisitStation): string {
    return station.owner.id === me.value ? 'Owned by you' : `Owned by ${station.owner.name}`
  }

  // --- Loading ----------------------------------------------------------------------------------

  let abort: AbortController | null = null

  async function fetchVisit (): Promise<void> {
    abort?.abort()
    const controller = new AbortController()
    abort = controller
    detailError.value = null
    try {
      detail.value = await visitsApi.get(visitId.value, controller.signal)
    } catch (error) {
      if (controller.signal.aborted) {
        return
      }
      // Out of scope and missing look the same (ADR-16: 404, not 403)
      detailError.value = error instanceof ApiError && (error.status === 404 || error.status === 422)
        ? 'missing'
        : (error instanceof NetworkError ? 'offline' : 'failed')
    }
  }

  async function reload (): Promise<void> {
    await fetchVisit()
  }

  watch(visitId, () => {
    detail.value = null
    void fetchVisit()
  }, { immediate: true })

  onBeforeUnmount(() => abort?.abort())
  onBeforeUnmount(forgetMediaLinks)

  // Not a phone, or the visit is not under way: the visit page is the place for it
  watch([detail, mdAndUp], ([visit, wide]) => {
    if (!leaving && visit && (wide || visit.status !== 'started')) {
      void router.replace({ name: 'visits', params: { id: visit.id } })
    }
  })

  // --- Moves -------------------------------------------------------------------------------------

  function changed (text: string, visit: VisitOut): void {
    detail.value = visit
    say(text)
  }

  const { busy, station: moveStation } = useVisitMoves({ visit: () => detail.value, changed, say, reload })

  /** Arriving opens the station's board (J6 step 3). */
  async function arrive (stationId: string): Promise<void> {
    await moveStation('arrive', stationId)
    if (detail.value?.stations.find(s => s.station_id === stationId)?.arrived_at) {
      await router.push({ name: 'visit-field', params: { id: visitId.value }, query: { station: stationId } })
    }
  }

  /** Departing returns to the stations (J6 step 7). */
  async function depart (stationId: string): Promise<void> {
    await moveStation('depart', stationId)
    if (detail.value?.stations.find(s => s.station_id === stationId)?.departed_at) {
      await router.push({ name: 'visit-field', params: { id: visitId.value } })
    }
  }

  /** Ending goes to Sync, where the files still on their way are counted (J6 step 9). */
  function ended (): void {
    leaving = true
    void router.replace({ name: 'sync' })
  }

  // --- Live (PRD NOT-5) --------------------------------------------------------------------------

  const refresh = settled(() => void fetchVisit())
  useLive(event => {
    if (event.entity === 'reconnected' || (isVisitUpdate(event) && event.id === visitId.value)) {
      refresh()
    }
  })
</script>
