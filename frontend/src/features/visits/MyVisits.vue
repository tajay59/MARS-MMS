<template>
  <section aria-labelledby="mv-h" class="flex max-w-2xl flex-col gap-2">
    <div class="flex items-baseline justify-between gap-3">
      <h2 id="mv-h" class="m-0 text-h3 text-surface-900">My upcoming visits</h2>
      <router-link class="text-sm font-medium text-primary no-underline hover:underline" :to="{ name: 'visits' }">All visits</router-link>
    </div>

    <FeedbackBanner v-if="error" type="error">{{ error }}</FeedbackBanner>

    <div v-else-if="loading" aria-label="Loading your visits…" role="status">
      <v-skeleton-loader type="list-item-two-line, list-item-two-line" />
    </div>

    <p v-else-if="visits.length === 0" class="m-0 text-surface-600">No visits planned for you. Visits you attend show here.</p>

    <ul v-else aria-label="My upcoming visits" class="m-0 flex list-none flex-col gap-0.5 p-0">
      <li v-for="visit in visits" :key="visit.id" class="relative flex flex-col gap-1 rounded-card px-3 py-2.5 hover:bg-surface-100">
        <span class="flex items-baseline justify-between gap-2">
          <span class="font-mono text-xs font-medium text-surface-600" translate="no">{{ visit.ref }}</span>
          <VisitStatusChip :status="visit.status" />
        </span>

        <router-link
          class="min-w-0 truncate font-medium text-surface-900 no-underline after:absolute after:inset-0 after:rounded-card focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
          :to="{ name: 'visits', params: { id: visit.id } }"
        >{{ visit.request_title }}</router-link>

        <span class="text-sm text-surface-600">{{ formatWhen(visit.planned_start, visitZone(visit)) }} · {{ stationNames(visit) }}</span>
      </li>
    </ul>
  </section>
</template>

<script lang="ts" setup>
  import type { VisitOut } from '@/api/models'
  import { onMounted, ref } from 'vue'
  import { visitsApi } from '@/api/operations'
  import { NetworkError } from '@/api/problem'
  import { isVisitUpdate, settled, useLive } from '@/app/composables/useLive'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import VisitStatusChip from '@/components/VisitStatusChip.vue'
  import { formatWhen, sortVisits, stationNames, visitZone } from './visits'

  // The dashboard's widget for technicians and admins (AFD "My upcoming visits"): the next few
  // visits they attend, planned or under way. It looks again when one changes (NOT-5).
  const SHOWN = 5
  const visits = ref<VisitOut[]>([])
  const loading = ref(true)
  const error = ref<string | null>(null)

  async function load (quiet = false): Promise<void> {
    try {
      visits.value = sortVisits((await visitsApi.mine()).items).slice(0, SHOWN)
      error.value = null
    } catch (error_) {
      if (!quiet) {
        error.value = error_ instanceof NetworkError
          ? 'This needs a connection. It will load when you have signal.'
          : 'We couldn’t load your visits. Reload the page to try again.'
      }
    } finally {
      loading.value = false
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
