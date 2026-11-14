<template>
  <div class="flex flex-col gap-4">
    <FeedbackBanner v-if="error" type="error">{{ error }}</FeedbackBanner>

    <div v-else-if="loading" aria-label="Loading visits…" class="flex flex-col gap-2" role="status">
      <v-skeleton-loader type="list-item-two-line, list-item-two-line" />
    </div>

    <p v-else-if="visits.length === 0" class="m-0 py-6 text-center text-surface-600">
      No visits yet.<template v-if="canSchedule"> Use Schedule visit to plan one.</template>
    </p>

    <template v-else>
      <div v-if="mdAndUp" class="overflow-x-auto">
        <table class="w-full border-collapse text-sm">
          <caption class="sr-only">Visits for this request, soonest first</caption>

          <thead>
            <tr class="bg-surface-100 text-left">
              <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Visit</th>
              <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">When</th>
              <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Lead</th>
              <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Status</th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="visit in visits" :key="visit.id" class="border-t border-surface-200">
              <td class="px-3 py-3">
                <router-link class="font-mono font-medium text-primary no-underline hover:underline" :to="{ name: 'visits', params: { id: visit.id } }" translate="no">{{ visit.ref }}</router-link>
                <div class="text-xs text-surface-600">{{ stationNames(visit) }}</div>
              </td>

              <td class="px-3 py-3 text-surface-900">{{ formatRange(visit.planned_start, visit.planned_end, visitZone(visit)) }}</td>
              <td class="whitespace-nowrap px-3 py-3 text-surface-900">{{ visit.lead.name }}</td>
              <td class="px-3 py-3"><VisitStatusChip :status="visit.status" /></td>
            </tr>
          </tbody>
        </table>
      </div>

      <ul v-else aria-label="Visits" class="m-0 flex list-none flex-col gap-1 p-0">
        <VisitCard v-for="visit in visits" :key="visit.id" :to="{ name: 'visits', params: { id: visit.id } }" :visit="visit" />
      </ul>

      <p class="m-0 rounded-lg bg-surface-50 px-3.5 py-3 text-sm text-surface-700">
        Two teams can work the same request at once, each on different stations. The request is <strong class="font-semibold text-surface-900">Scheduled</strong> until one starts, then <strong class="font-semibold text-surface-900">In progress</strong>.
      </p>
    </template>
  </div>
</template>

<script lang="ts" setup>
  import type { VisitOut } from '@/api/models'
  import { onMounted, ref, watch } from 'vue'
  import { useDisplay } from 'vuetify'
  import { visitsApi } from '@/api/operations'
  import { NetworkError } from '@/api/problem'
  import { isVisitUpdate, settled, useLive } from '@/app/composables/useLive'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import VisitStatusChip from '@/components/VisitStatusChip.vue'
  import VisitCard from './VisitCard.vue'
  import { formatRange, sortVisits, stationNames, visitZone } from './visits'

  // The request page's Visits tab (AFD J5; PRD VIS-11): every visit of the request, soonest first.
  // A client sees the same list, with names and times and no notes. It looks again when a visit of
  // this request changes anywhere (NOT-5).
  const props = defineProps<{ requestId: string, canSchedule: boolean, refreshKey?: number }>()
  const emit = defineEmits<{ count: [live: number] }>()

  const { mdAndUp } = useDisplay()
  const visits = ref<VisitOut[]>([])
  const loading = ref(true)
  const error = ref<string | null>(null)

  async function load (quiet = false): Promise<void> {
    if (!quiet) {
      loading.value = true
      error.value = null
    }
    try {
      const page = await visitsApi.list({ request_id: props.requestId, limit: 200 })
      visits.value = sortVisits(page.items)
      emit('count', page.items.filter(v => v.status !== 'cancelled').length)
    } catch (error_) {
      if (!quiet) {
        error.value = error_ instanceof NetworkError
          ? 'This needs a connection. It will load when you have signal.'
          : 'We couldn’t load the visits. Reload the page to try again.'
      }
    } finally {
      loading.value = false
    }
  }

  const refresh = settled(() => {
    void load(true)
  })

  useLive(event => {
    if (event.entity === 'reconnected' || (isVisitUpdate(event) && event.request_id === props.requestId)) {
      refresh()
    }
  })

  watch(() => [props.requestId, props.refreshKey], () => {
    void load()
  })
  onMounted(() => load())
</script>
