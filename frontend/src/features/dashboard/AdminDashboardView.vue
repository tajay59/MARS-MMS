<template>
  <div class="flex flex-col gap-5">
    <section aria-label="Needs attention" class="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-6">
      <KpiTile
        v-if="isAdmin"
        label="Registrations pending"
        link="Review them"
        :to="{ name: 'admin-registrations' }"
        :tone="toneOf(registrations.pending, 'amber')"
        :value="registrations.pending"
      />

      <KpiTile
        label="Requests awaiting approval"
        link="Open the list"
        :loading="loading"
        :to="{ name: 'requests', query: { status: 'submitted' } }"
        :unavailable="unavailable"
        :value="figures?.requests_awaiting_approval"
      />

      <KpiTile
        label="Unassigned queue"
        link="Open the queue"
        :loading="loading"
        :to="canWork ? { name: 'queue' } : { name: 'requests', query: { status: 'approved' } }"
        :unavailable="unavailable"
        :value="figures?.unassigned_queue"
      />

      <KpiTile
        label="In Client Review"
        link="See them"
        :loading="loading"
        :to="{ name: 'requests', query: { status: 'client_review' } }"
        :unavailable="unavailable"
        :value="figures?.in_client_review"
      />

      <KpiTile
        :caption="calibrationCaption"
        label="Calibrations due or overdue"
        link="Calibration due"
        :loading="loading"
        :to="{ name: 'calibration' }"
        :tone="toneOf(figures?.calibrations_overdue, 'amber')"
        :unavailable="unavailable"
        :value="calibrationTotal"
      />

      <KpiTile
        label="Failed calibrations"
        link="Follow up"
        :loading="loading"
        :to="{ name: 'calibration' }"
        :tone="toneOf(figures?.failed_calibrations, 'red')"
        :unavailable="unavailable"
        :value="figures?.failed_calibrations"
      />
    </section>

    <div class="grid gap-4 xl:grid-cols-2">
      <section aria-labelledby="by-status-h" class="flex min-w-0 flex-col gap-3 rounded-card bg-surface-50 p-5">
        <div class="flex items-baseline justify-between gap-3">
          <h2 id="by-status-h" class="m-0 text-h3 text-surface-900">Open requests by status</h2>
          <span v-if="data && !unavailable" class="text-xs text-surface-600">{{ openTotal }} open</span>
        </div>

        <p v-if="unavailable" class="m-0 text-sm text-surface-600">Needs a connection.</p>
        <v-skeleton-loader v-else-if="loading" type="list-item, list-item, list-item" />
        <StatusBars v-else :counts="data?.requests_by_status ?? []" />
      </section>

      <section aria-labelledby="by-country-h" class="flex min-w-0 flex-col gap-3 rounded-card bg-surface-50 p-5">
        <div class="flex items-baseline justify-between gap-3">
          <h2 id="by-country-h" class="m-0 text-h3 text-surface-900">Stations by status and country</h2>
          <span v-if="data && !unavailable" class="text-xs text-surface-600">{{ stationTotal }} stations</span>
        </div>

        <p v-if="unavailable" class="m-0 text-sm text-surface-600">Needs a connection.</p>
        <v-skeleton-loader v-else-if="loading" type="table-row, table-row, table-row" />
        <p v-else-if="!data?.stations_by_country.length" class="m-0 text-sm text-surface-600">No stations yet.</p>

        <div v-else class="overflow-x-auto">
          <table class="w-full border-collapse text-sm">
            <thead>
              <tr class="text-left text-xs text-surface-600">
                <th class="py-2 pr-3 font-semibold" scope="col">Country</th>
                <th class="px-2 py-2 text-right font-semibold" scope="col">Operational</th>
                <th class="px-2 py-2 text-right font-semibold" scope="col">Degraded</th>
                <th class="px-2 py-2 text-right font-semibold" scope="col">Offline</th>
                <th class="py-2 pl-2 text-right font-semibold" scope="col">Total</th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="row in data.stations_by_country" :key="row.country" class="border-t border-surface-200">
                <th class="py-2 pr-3 text-left font-normal text-surface-900" scope="row">{{ row.country }}</th>
                <td class="px-2 py-2 text-right"><StationCount :count="row.operational" status="operational" /></td>
                <td class="px-2 py-2 text-right"><StationCount :count="row.degraded" status="degraded" /></td>
                <td class="px-2 py-2 text-right"><StationCount :count="row.offline" status="offline" /></td>
                <td class="py-2 pl-2 text-right font-semibold tabular-nums text-surface-900">{{ row.total }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <div class="grid gap-4 xl:grid-cols-2">
      <UpcomingVisits />

      <section aria-labelledby="awaiting-h" class="flex min-w-0 flex-col gap-2 rounded-card bg-surface-50 p-5">
        <div class="flex items-baseline justify-between gap-3">
          <h2 id="awaiting-h" class="m-0 text-h3 text-surface-900">Reports awaiting finalization</h2>
          <span v-if="figures && !unavailable" class="text-xs text-surface-600">{{ figures.reports_awaiting_finalization }} in all</span>
        </div>

        <p v-if="unavailable" class="m-0 text-sm text-surface-600">Needs a connection.</p>
        <v-skeleton-loader v-else-if="loading" type="list-item-two-line, list-item-two-line" />
        <p v-else-if="!data?.reports_awaiting.length" class="m-0 text-sm text-surface-600">Every report is final.</p>
        <AwaitingReports v-else :reports="data.reports_awaiting" :staff="canWork" />
      </section>
    </div>
  </div>
</template>

<script lang="ts" setup>
  import type { AdminDashboard } from '@/api/models'
  import { storeToRefs } from 'pinia'
  import { computed, onMounted } from 'vue'
  import { useRegistrationsStore } from '@/stores/registrations'
  import { useSessionStore } from '@/stores/session'
  import AwaitingReports from './AwaitingReports.vue'
  import { toneOf } from './dashboard'
  import KpiTile from './KpiTile.vue'
  import StationCount from './StationCount.vue'
  import StatusBars from './StatusBars.vue'
  import UpcomingVisits from './UpcomingVisits.vue'

  // The admin's dashboard, and the Viewer's with the actions left out (DBD "Dashboards"; SUM-4).
  const props = defineProps<{ data: AdminDashboard | null, loading: boolean, unavailable: boolean }>()

  const session = useSessionStore()
  const { isAdmin } = storeToRefs(session)
  const registrations = useRegistrationsStore()
  // The queue is for people who can claim from it; a Viewer's tile opens the approved requests
  const canWork = computed(() => session.hasAnyRole(['technician', 'admin']))

  const figures = computed(() => props.data?.figures ?? null)
  const calibrationTotal = computed(() => figures.value
    ? figures.value.calibrations_overdue + figures.value.calibrations_due_soon
    : null)
  const calibrationCaption = computed(() => figures.value
    ? `${figures.value.calibrations_overdue} overdue, ${figures.value.calibrations_due_soon} due in 30 days`
    : undefined)
  const openTotal = computed(() => (props.data?.requests_by_status ?? []).reduce((sum, r) => sum + r.count, 0))
  const stationTotal = computed(() => (props.data?.stations_by_country ?? []).reduce((sum, r) => sum + r.total, 0))

  onMounted(() => {
    if (isAdmin.value) {
      void registrations.refresh()
    }
  })
</script>
