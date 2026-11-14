<template>
  <section :aria-labelledby="id" class="flex min-w-0 flex-col gap-2 rounded-card bg-surface-50 p-5">
    <div class="flex items-baseline justify-between gap-3">
      <h2 :id="id" class="m-0 text-h3 text-surface-900">{{ title }}</h2>
      <router-link class="inline-flex min-h-6 items-center text-sm font-medium text-primary no-underline hover:underline" :to="{ name: 'visits' }">All visits<span aria-hidden="true"> →</span></router-link>
    </div>

    <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

    <div v-else-if="loading" aria-label="Loading visits…" role="status">
      <v-skeleton-loader type="list-item-two-line, list-item-two-line" />
    </div>

    <p v-else-if="visits.length === 0" class="m-0 text-sm text-surface-600">{{ empty }}</p>

    <ul v-else :aria-label="title" class="m-0 flex list-none flex-col p-0">
      <li v-for="visit in visits" :key="visit.id" class="relative flex items-center gap-3 border-b border-surface-200 py-2.5 last:border-b-0">
        <v-icon aria-hidden="true" class="text-surface-600" :icon="mdiCalendarBlankOutline" size="20" />

        <span class="flex min-w-0 grow flex-col">
          <router-link
            class="truncate font-medium text-surface-900 no-underline hover:underline after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-primary"
            :to="{ name: 'visits', params: { id: visit.id } }"
          >{{ stationNames(visit) }}</router-link>

          <span class="truncate text-xs text-surface-600">
            <span class="font-mono" translate="no">{{ visit.ref }}</span><template v-if="showLead"> · {{ visit.lead.name }}</template>
          </span>
        </span>

        <span v-if="readyOffline.has(visit.id)" class="inline-flex h-6 shrink-0 items-center gap-1 rounded-full bg-success-container pl-2 pr-2.5 text-xs font-medium text-on-success-container">
          <v-icon :icon="mdiCheck" size="14" />Ready offline
        </span>

        <span class="shrink-0 text-sm text-surface-600">{{ formatWhen(visit.planned_start, visitZone(visit)) }}</span>
      </li>
    </ul>
  </section>
</template>

<script lang="ts" setup>
  import type { VisitOut } from '@/api/models'
  import { mdiCalendarBlankOutline, mdiCheck } from '@mdi/js'
  import { onMounted, ref, useId } from 'vue'
  import { visitsApi } from '@/api/operations'
  import { NetworkError } from '@/api/problem'
  import { isVisitUpdate, settled, useLive } from '@/app/composables/useLive'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { preparedVisits } from '@/offline/prepared'
  import { useSessionStore } from '@/stores/session'
  import { formatWhen, stationNames, visitZone } from '../visits/visits'

  // The next few planned visits (SUM-4, SUM-6). A person's own on a technician's page, everyone's
  // for an admin, the organization's for a client: the server scopes what comes back. On a phone
  // the ones prepared there say so, from the phone's own database (OFF-9).
  const props = withDefaults(defineProps<{
    title?: string
    mine?: boolean
    showLead?: boolean
    empty?: string
  }>(), { title: 'Upcoming visits', mine: false, showLead: true, empty: 'No visits are planned.' })

  const SHOWN = 5
  const id = useId()
  const session = useSessionStore()
  const visits = ref<VisitOut[]>([])
  const readyOffline = ref(new Set<string>())
  const loading = ref(true)
  const problem = ref<string | null>(null)

  async function load (quiet = false): Promise<void> {
    try {
      const page = props.mine
        ? await visitsApi.mine()
        : await visitsApi.list({ status: 'planned', from: new Date().toISOString(), limit: SHOWN })
      visits.value = page.items
        .filter(v => v.status === 'planned' || v.status === 'started')
        .toSorted((a, b) => a.planned_start.localeCompare(b.planned_start))
        .slice(0, SHOWN)
      problem.value = null
    } catch (error) {
      if (!quiet) {
        problem.value = error instanceof NetworkError
          ? 'This needs a connection. It will load when you have signal.'
          : 'We couldn’t load the visits. Reload the page to try again.'
      }
    } finally {
      loading.value = false
    }
    const userId = session.user?.id
    if (props.mine && userId) {
      readyOffline.value = new Set((await preparedVisits(userId)).filter(p => p.row.ready).map(p => p.bundle.visit.id))
    }
  }

  const refresh = settled(() => {
    void load(true)
  })

  useLive(event => {
    if (event.entity === 'reconnected' || isVisitUpdate(event)) {
      refresh()
    }
  })

  onMounted(() => load())
</script>
