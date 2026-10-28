<template>
  <div class="flex flex-col gap-5">
    <FeedbackBanner v-if="unavailable" :icon="mdiCloudOffOutline" type="info">
      <p class="m-0 font-medium">No signal</p>
      <p class="m-0 text-xs">The figures from the server need a connection. Visits prepared on this phone still open.</p>
    </FeedbackBanner>

    <section aria-label="Your figures" class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
      <KpiTile
        compact
        label="My assigned"
        link="Open"
        :loading="loading"
        :to="{ name: 'requests' }"
        :unavailable="unavailable"
        :value="figures?.my_assigned"
      />

      <KpiTile
        compact
        label="Queue"
        link="Open"
        :loading="loading"
        :to="{ name: 'queue' }"
        :unavailable="unavailable"
        :value="figures?.queue"
      />

      <KpiTile
        :caption="readyCaption"
        compact
        label="My upcoming visits"
        link="Open"
        :loading="loading && !unavailable"
        :to="{ name: 'visits' }"
        :value="unavailable ? prepared : figures?.my_upcoming_visits"
      />
      <!-- From this phone's own database, so it is true with no signal too -->
      <KpiTile
        compact
        label="Waiting to sync"
        link="Open Sync"
        :loading="!sync.ready.value"
        :to="{ name: 'sync' }"
        :tone="toneOf(waitingToSync, 'amber')"
        :value="waitingToSync"
      />

      <KpiTile
        class="col-span-2 sm:col-span-1"
        compact
        label="Reports to finalize"
        link="Open"
        :loading="loading"
        :to="{ name: 'reports' }"
        :unavailable="unavailable"
        :value="figures?.my_reports_to_finalize"
      />
    </section>

    <div class="grid gap-4 xl:grid-cols-2">
      <UpcomingVisits mine :show-lead="false" title="My upcoming visits" />

      <section aria-labelledby="mine-h" class="flex min-w-0 flex-col gap-2 rounded-card bg-surface-50 p-5">
        <h2 id="mine-h" class="m-0 text-h3 text-surface-900">My reports to finalize</h2>
        <p v-if="unavailable" class="m-0 text-sm text-surface-600">Needs a connection.</p>
        <v-skeleton-loader v-else-if="loading" type="list-item-two-line" />
        <p v-else-if="!data?.reports_to_finalize.length" class="m-0 text-sm text-surface-600">Nothing waits for your signature.</p>
        <AwaitingReports v-else :reports="data.reports_to_finalize" staff />
      </section>
    </div>
  </div>
</template>

<script lang="ts" setup>
  import type { TechnicianDashboard } from '@/api/models'
  import { mdiCloudOffOutline } from '@mdi/js'
  import { computed, onMounted, ref } from 'vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { useSyncOverview } from '@/features/field/useSyncOverview'
  import { preparedVisits } from '@/offline/prepared'
  import { useSessionStore } from '@/stores/session'
  import AwaitingReports from './AwaitingReports.vue'
  import { toneOf } from './dashboard'
  import KpiTile from './KpiTile.vue'
  import UpcomingVisits from './UpcomingVisits.vue'

  // The technician dashboard (SUM-5; DBD "Dashboards"), phone first. Four tiles are the server's
  // and need a connection; "Waiting to sync" and the count of visits ready on this phone come from
  // the phone's own database, so they are true with no signal (OFF-6, OFF-9).
  const props = defineProps<{ data: TechnicianDashboard | null, loading: boolean, unavailable: boolean }>()

  const session = useSessionStore()
  const sync = useSyncOverview()
  const prepared = ref<number | null>(null)

  const figures = computed(() => props.data?.figures ?? null)
  const waitingToSync = computed(() => sync.ready.value ? sync.totals.value.changes + sync.totals.value.files : null)
  const readyCaption = computed(() => props.unavailable ? 'ready on this phone' : undefined)

  onMounted(async () => {
    const id = session.user?.id
    prepared.value = id ? (await preparedVisits(id)).filter(p => p.row.ready).length : 0
  })
</script>
