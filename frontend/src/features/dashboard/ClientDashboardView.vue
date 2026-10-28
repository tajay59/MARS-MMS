<template>
  <div class="flex flex-col gap-5">
    <FeedbackBanner v-if="reviewing" type="warning">
      <div class="flex flex-wrap items-center gap-3">
        <div class="min-w-0 grow">
          <p class="m-0 font-semibold">{{ reviewing === 1 ? '1 request is waiting for your review' : `${reviewing} requests are waiting for your review` }}</p>
          <p class="m-0 text-xs">Read the reports, then accept the work or send it back. A request closes on its own 30 days after review starts.</p>
        </div>

        <v-btn color="primary" size="small" :to="{ name: 'requests', query: { status: 'client_review' } }">Review {{ reviewing === 1 ? 'it' : 'them' }}</v-btn>
      </div>
    </FeedbackBanner>

    <section aria-labelledby="stations-h" class="flex flex-col gap-2.5">
      <h2 id="stations-h" class="m-0 text-h3 text-surface-900">Our stations by status</h2>

      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div v-for="s in statuses" :key="s" class="flex min-w-0 flex-col gap-1 rounded-card bg-surface-50 px-4 py-3.5">
          <StationStatusChip class="self-start" :status="s" />

          <div class="font-heading text-kpi tabular-nums text-surface-900">
            <template v-if="unavailable">
              <span aria-hidden="true" class="text-surface-500">–</span>
              <span class="sr-only">Needs a connection</span>
            </template>

            <v-skeleton-loader v-else-if="loading" class="my-1 w-12" type="text" />
            <template v-else>{{ data?.stations[s] ?? 0 }}</template>
          </div>

          <router-link
            v-if="!unavailable && !loading && (data?.stations[s] ?? 0) > 0"
            class="inline-flex min-h-6 w-fit items-center text-sm font-medium text-primary no-underline hover:underline"
            :to="{ name: 'stations', query: { status: s } }"
          >See {{ data?.stations[s] === 1 ? 'it' : 'them' }}<span aria-hidden="true"> →</span></router-link>

          <span v-else-if="!unavailable && !loading" class="text-xs text-surface-600">None</span>
        </div>
      </div>
    </section>

    <div class="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
      <section aria-labelledby="open-h" class="flex min-w-0 flex-col gap-2 rounded-card bg-surface-50 p-5">
        <div class="flex items-baseline justify-between gap-3">
          <h2 id="open-h" class="m-0 text-h3 text-surface-900">Open requests</h2>
          <router-link class="inline-flex min-h-6 items-center text-sm font-medium text-primary no-underline hover:underline" :to="{ name: 'requests' }">All requests<span aria-hidden="true"> →</span></router-link>
        </div>

        <FeedbackBanner v-if="requestsProblem" type="error">{{ requestsProblem }}</FeedbackBanner>
        <v-skeleton-loader v-else-if="requestsLoading" type="table-row, table-row, table-row" />
        <p v-else-if="requests.length === 0" class="m-0 text-sm text-surface-600">Nothing is open. Report a problem when one comes up.</p>

        <ul v-else aria-label="Open requests" class="m-0 flex list-none flex-col p-0">
          <li v-for="r in requests" :key="r.id" class="relative flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-surface-200 py-2.5 last:border-b-0">
            <router-link
              class="min-w-0 grow basis-48 truncate font-medium text-surface-900 no-underline hover:underline after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-primary"
              :to="{ name: 'requests', params: { id: r.id } }"
            >{{ r.title }}</router-link>

            <span class="font-mono text-xs text-surface-600" translate="no">{{ stationsLabel(r) }}</span>
            <RequestStatusChip :status="r.status" />
            <span class="w-16 text-right text-xs text-surface-600">{{ formatListTime(r.updated_at) }}</span>
          </li>
        </ul>
      </section>

      <div class="flex min-w-0 flex-col gap-4">
        <UpcomingVisits />

        <section aria-labelledby="recent-h" class="flex min-w-0 flex-col gap-2 rounded-card bg-surface-50 p-5">
          <div class="flex items-baseline justify-between gap-3">
            <h2 id="recent-h" class="m-0 text-h3 text-surface-900">Recent reports</h2>
            <router-link class="inline-flex min-h-6 items-center text-sm font-medium text-primary no-underline hover:underline" :to="{ name: 'reports' }">All reports<span aria-hidden="true"> →</span></router-link>
          </div>

          <p v-if="unavailable" class="m-0 text-sm text-surface-600">Needs a connection.</p>
          <v-skeleton-loader v-else-if="loading" type="list-item-two-line" />
          <p v-else-if="!data?.recent_reports.length" class="m-0 text-sm text-surface-600">Reports appear here once a visit report is final.</p>

          <ul v-else aria-label="Recent reports" class="m-0 flex list-none flex-col p-0">
            <li v-for="r in data.recent_reports" :key="r.report_id" class="relative flex items-center gap-3 border-b border-surface-200 py-2.5 last:border-b-0">
              <v-icon aria-hidden="true" class="text-surface-600" :icon="mdiFileDocumentOutline" size="20" />

              <span class="flex min-w-0 grow flex-col">
                <component
                  :is="r.request_id ? 'router-link' : 'span'"
                  class="truncate font-medium text-surface-900 no-underline hover:underline after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-primary"
                  v-bind="r.request_id ? { to: { name: 'requests', params: { id: r.request_id }, query: { tab: 'reports' } } } : {}"
                >{{ kindLabel[r.type] ?? 'Report' }} <span class="font-mono" translate="no">{{ r.number }}</span></component>

                <span class="text-xs text-surface-600">{{ r.finalized_at ? formatDate(r.finalized_at) : '' }}</span>
              </span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
  import type { ClientDashboard, RequestSummary } from '@/api/models'
  import { mdiFileDocumentOutline } from '@mdi/js'
  import { computed, onMounted, ref } from 'vue'
  import { requestsApi } from '@/api/operations'
  import { NetworkError } from '@/api/problem'
  import { formatDate, formatListTime } from '@/app/format'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import RequestStatusChip from '@/components/RequestStatusChip.vue'
  import StationStatusChip from '@/components/StationStatusChip.vue'
  import { stationsLabel } from '@/features/requests/requests'
  import { isOpen } from './dashboard'
  import UpcomingVisits from './UpcomingVisits.vue'

  // The client dashboard (SUM-6; DBD "Dashboards"). Numbers come from the report service, scoped
  // to their organization on the server; the open requests are the requests list, which is scoped
  // the same way and has the titles.
  const props = defineProps<{ data: ClientDashboard | null, loading: boolean, unavailable: boolean }>()

  const SHOWN = 5
  const statuses = ['operational', 'degraded', 'offline', 'decommissioned'] as const
  const kindLabel: Record<string, string> = {
    visit: 'Visit report', closeout: 'Close-out report', client_form: 'Your report',
  }

  const requests = ref<RequestSummary[]>([])
  const requestsLoading = ref(true)
  const requestsProblem = ref<string | null>(null)
  const reviewing = computed(() => props.data?.figures.awaiting_our_review ?? 0)

  onMounted(async () => {
    try {
      const page = await requestsApi.list({ limit: 50 })
      requests.value = page.items.filter(r => isOpen(r.status)).slice(0, SHOWN)
    } catch (error) {
      requestsProblem.value = error instanceof NetworkError
        ? 'This needs a connection. It will load when you have signal.'
        : 'We couldn’t load your requests. Reload the page to try again.'
    } finally {
      requestsLoading.value = false
    }
  })
</script>
