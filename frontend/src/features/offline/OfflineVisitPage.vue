<template>
  <PageBody :back="{ name: 'sync' }" :subtitle="subtitle" :title="found?.bundle.visit.ref ?? 'Visit'">
    <div class="flex flex-col gap-4 p-4 md:p-0">
      <FeedbackBanner type="warning">
        No connection. You can read this visit. Recording with no signal is not ready yet, so nothing can be saved.
      </FeedbackBanner>

      <div v-if="loading" aria-label="Loading the visit…" class="flex flex-col gap-3" role="status">
        <v-skeleton-loader type="heading, list-item-two-line, list-item-two-line" />
      </div>

      <ScanCard v-else-if="!found" :icon="mdiMapMarkerOffOutline" title="This visit is not on your phone" tone="neutral">
        Prepare it with a connection before you go.
      </ScanCard>

      <template v-else>
        <section aria-labelledby="ov-visit-h" class="flex flex-col gap-2 rounded-card bg-surface-50 p-4">
          <div class="flex items-center gap-2">
            <h2 id="ov-visit-h" class="m-0 grow text-h3 text-surface-900">{{ found.bundle.request.title }}</h2>

            <span class="inline-flex items-center gap-1.5 rounded-full bg-success-container px-2.5 py-1 text-sm font-semibold text-on-success-container">
              <v-icon :icon="mdiCheck" size="16" />Ready offline
            </span>
          </div>

          <p class="m-0 text-sm text-surface-600">{{ formatRange(visit.planned_start, visit.planned_end, zone) }}</p>
          <p class="m-0 text-sm text-surface-600">Prepared {{ ago }}.</p>
        </section>

        <section aria-labelledby="ov-stations-h" class="flex flex-col gap-2">
          <h2 id="ov-stations-h" class="m-0 text-h3 text-surface-900">Stations</h2>

          <ul class="m-0 flex list-none flex-col gap-2 p-0" role="list">
            <li v-for="item in found.bundle.stations" :key="item.station.id" class="flex flex-col gap-2 rounded-card bg-surface-50 p-4">
              <router-link class="flex flex-col gap-0.5 text-surface-900 no-underline" :to="{ name: 'stations', params: { id: item.station.id } }">
                <span class="font-medium">{{ item.station.name }}</span>
                <span class="font-mono text-xs text-surface-600" translate="no">{{ item.station.code }}</span>
                <span class="text-sm text-surface-600">{{ ownerLine(item.station.id) }}</span>
              </router-link>

              <ul v-if="item.board.length > 0" :aria-label="`Board for ${item.station.name}`" class="m-0 flex list-none flex-col gap-1.5 p-0">
                <li v-for="element in item.board" :key="element.id" class="flex items-baseline gap-2 text-sm">
                  <span class="shrink-0 rounded-full bg-surface-200 px-2 py-0.5 text-xs font-medium text-surface-800">{{ kinds[element.kind] }}</span>
                  <span class="min-w-0 break-words text-surface-900">{{ element.title }}</span>
                </li>
              </ul>

              <p v-else class="m-0 text-sm text-surface-600">Nothing on this board yet.</p>
            </li>
          </ul>
        </section>
      </template>
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { Prepared } from '@/offline/prepared'
  import { mdiCheck, mdiMapMarkerOffOutline } from '@mdi/js'
  import { computed, onMounted, ref } from 'vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import ScanCard from '@/features/scan/ScanCard.vue'
  import { formatRange, visitZone } from '@/features/visits/visits'
  import { preparedVisit } from '@/offline/prepared'
  import { useSessionStore } from '@/stores/session'
  import { preparedAgo } from './preparedAgo'

  // A prepared visit with no signal (OFF-2; W13-13): the request, the stations and their boards as
  // they were when it was prepared. Read only until the outbox arrives in W14.
  const props = defineProps<{ id: string }>()
  const session = useSessionStore()

  const loading = ref(true)
  const found = ref<Prepared | null>(null)

  const visit = computed(() => found.value!.bundle.visit)
  const zone = computed(() => visitZone(visit.value))
  const ago = computed(() => (found.value ? preparedAgo(found.value.row.prepared_at) : ''))
  const subtitle = computed(() => found.value?.bundle.request.title)

  const kinds: Record<string, string> = { note: 'Note', task: 'Task', recommendation: 'Recommendation', config: 'Config' }

  function ownerLine (stationId: string): string {
    const entry = visit.value.stations.find(s => s.station_id === stationId)
    if (!entry) {
      return ''
    }
    return entry.owner.id === session.user?.id ? 'You own this station' : `${entry.owner.name} owns this station`
  }

  onMounted(async () => {
    const me = session.user
    if (me) {
      found.value = await preparedVisit(me.id, props.id)
    }
    loading.value = false
  })
</script>
