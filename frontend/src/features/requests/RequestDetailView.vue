<template>
  <div class="flex flex-col">
    <!-- At most one banner for the current state (DBD "Request page") -->
    <div v-if="banner" class="mb-4">
      <FeedbackBanner :icon="banner.tone === 'error' ? mdiCancel : (banner.tone === 'neutral' ? mdiCloseCircleOutline : undefined)" :type="banner.tone === 'error' ? 'error' : 'info'">
        <p class="m-0 font-medium">{{ banner.title }}</p>
        <p v-if="banner.body" class="m-0 mt-0.5">{{ banner.body }}</p>
      </FeedbackBanner>
    </div>

    <!-- Phones: the tabs live in the page's pinned header (PageBody), so the page scrolls under them -->
    <Teleport :disabled="!pageBar" :to="pageBar ?? 'body'">
      <v-tabs
        v-model="tab"
        :class="pageBar ? 'bg-transparent' : '-mx-4 border-b border-surface-200 md:-mx-8'"
        color="primary"
        density="comfortable"
        :show-arrows="mdAndUp"
      >
        <v-tab v-for="t in tabs" :key="t.key" class="px-4 md:first:ml-4" :value="t.key">
          {{ t.label }}<span v-if="t.key === 'comments' && commentCount > 0" class="ml-1.5 tabular-nums text-surface-600">{{ commentCount }}</span>
        </v-tab>
      </v-tabs>
    </Teleport>

    <v-tabs-window v-model="tab" class="pt-6">
      <v-tabs-window-item value="overview">
        <div class="grid gap-8 lg:grid-cols-[minmax(0,1fr)_280px]">
          <!-- Smaller screens: the status comes first (DBD) -->
          <aside aria-labelledby="req-status-h" class="min-w-0 lg:order-2">
            <h2 id="req-status-h" class="m-0 mb-3 text-h3 text-surface-900">Status</h2>

            <ol class="m-0 flex list-none flex-col p-0">
              <li
                v-for="(step, index) in steps"
                :key="`${step.status}-${index}`"
                class="relative grid grid-cols-[22px_minmax(0,1fr)] gap-3 pb-4 last:pb-0"
                :class="index < steps.length - 1 ? 'before:absolute before:bottom-0 before:left-2.5 before:top-5.5 before:w-0.5 before:bg-surface-200' : ''"
              >
                <span v-if="!step.future" aria-hidden="true" class="grid size-5.5 place-items-center rounded-full" :class="lookOf(step.status).dot">
                  <v-icon :icon="lookOf(step.status).icon" size="14" />
                </span>

                <span v-else aria-hidden="true" class="size-5.5 rounded-full border-2 border-surface-300" />

                <span class="flex min-w-0 flex-col">
                  <span :class="step.future ? 'text-surface-500' : 'font-medium text-surface-900'">
                    {{ lookOf(step.status).label }}<template v-if="step.current"> · now</template>
                    <span v-if="step.future" class="sr-only"> (not yet)</span>
                  </span>

                  <span v-if="step.at" class="text-sm text-surface-600">{{ formatDateTime(step.at) }}</span>
                </span>
              </li>
            </ol>
          </aside>

          <dl class="m-0 grid min-w-0 grid-cols-[110px_minmax(0,1fr)] text-sm sm:grid-cols-[140px_minmax(0,1fr)] lg:order-1">
            <template v-for="(row, i) in facts" :key="row.label">
              <dt class="py-2.5 text-surface-600" :class="i > 0 ? 'border-t border-surface-200' : ''">{{ row.label }}</dt>

              <dd class="m-0 min-w-0 py-2.5 text-surface-900" :class="i > 0 ? 'border-t border-surface-200' : ''">
                <span v-if="row.label === 'Stations'" class="flex flex-wrap gap-1.5">
                  <router-link
                    v-for="s in detail.stations"
                    :key="s.id"
                    class="inline-flex h-7 items-center gap-1.5 rounded-full bg-surface-100 px-2.5 text-surface-900 no-underline hover:bg-surface-200"
                    :to="{ name: 'stations', params: { id: s.id } }"
                  >
                    <span class="font-mono text-xs font-medium" translate="no">{{ s.code }}</span>
                    <span class="text-sm">{{ s.name }}</span>
                  </router-link>
                </span>

                <span v-else-if="row.label === 'Files'" class="flex flex-wrap gap-1.5">
                  <SavedFile v-for="file in detail.attachments" :key="file.media_id" :file="file" :link="() => linkFor(file.media_id)" />
                </span>

                <span v-else class="wrap-break-word whitespace-pre-line" :class="row.muted ? 'text-surface-600' : ''">{{ row.value }}</span>
              </dd>
            </template>
          </dl>
        </div>
      </v-tabs-window-item>

      <v-tabs-window-item value="comments">
        <RequestComments :request-id="detail.id" @count="seen = $event" />
      </v-tabs-window-item>

      <v-tabs-window-item value="history">
        <div class="overflow-x-auto">
          <table class="w-full border-collapse text-sm">
            <caption class="sr-only">Status history, oldest first</caption>

            <thead>
              <tr class="bg-surface-100 text-left">
                <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">From</th>
                <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">To</th>
                <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">By</th>
                <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">When</th>
                <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Note</th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="(entry, i) in detail.status_history" :key="i" class="h-13 border-t border-surface-200">
                <td class="px-3"><RequestStatusChip v-if="entry.from_status" :status="entry.from_status" /><span v-else class="text-surface-500">—</span></td>
                <td class="px-3"><RequestStatusChip :status="entry.to_status" /></td>
                <td class="whitespace-nowrap px-3 text-surface-900">{{ entry.by?.name ?? 'System' }}</td>
                <td class="whitespace-nowrap px-3 tabular-nums text-surface-600">{{ formatDateTime(entry.at) }}</td>
                <td class="min-w-60 px-3 py-2 text-surface-900">{{ entry.note ?? '' }}<span v-if="!entry.note" class="text-surface-500">—</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </v-tabs-window-item>
    </v-tabs-window>
  </div>
</template>

<script lang="ts" setup>
  import type { RequestDetail } from '@/api/models'
  import { mdiCancel, mdiCloseCircleOutline } from '@mdi/js'
  import { computed, inject, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { requestsApi } from '@/api/operations'
  import { formatDateTime } from '@/app/format'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { pageBarKey } from '@/components/pageBar'
  import RequestStatusChip from '@/components/RequestStatusChip.vue'
  import RequestComments from './RequestComments.vue'
  import { bannerFor, categoryLabel, lookOf, timelineOf } from './requests'
  import SavedFile from './SavedFile.vue'

  // The body of /requests/:id (DBD "Request page"): the status timeline and the facts, the comments
  // and the history of every change. Visits and Reports join the tabs when those features exist.
  const props = defineProps<{ detail: RequestDetail, isClient: boolean }>()

  const route = useRoute()
  const router = useRouter()
  const { mdAndUp } = useDisplay()
  const pageBar = inject(pageBarKey, ref<HTMLElement | null>(null))

  const tabs = [
    { key: 'overview', label: 'Overview' },
    { key: 'comments', label: 'Comments' },
    { key: 'history', label: 'History' },
  ]

  // The tab is in the URL (?tab=history)
  const tab = computed<string>({
    get: () => {
      const value = route.query.tab
      return typeof value === 'string' && tabs.some(t => t.key === value) ? value : 'overview'
    },
    set: value => {
      void router.replace({ query: { ...route.query, tab: value === 'overview' ? undefined : value } })
    },
  })

  // The number on the tab: what the page was told, then what the thread says once it has loaded
  const seen = ref<number | null>(null)
  const commentCount = computed(() => seen.value ?? props.detail.comment_count)

  function linkFor (mediaId: string): Promise<{ url: string }> {
    return requestsApi.requestFile(props.detail.id, mediaId)
  }

  const banner = computed(() => bannerFor(props.detail, props.isClient))
  const steps = computed(() => timelineOf(props.detail.status_history, props.detail.status))

  interface Fact { label: string, value?: string, muted?: boolean }

  const facts = computed<Fact[]>(() => {
    const d = props.detail
    const assigned = d.assigned_staff.map(p => p.name).join(', ')
    return [
      { label: 'Category', value: categoryLabel(d.category) },
      { label: 'Stations' },
      { label: 'Requested by', value: [d.requested_by?.name, d.org_name].filter(Boolean).join(' · ') || '—' },
      { label: 'Submitted', value: formatDateTime(d.milestones.submitted_at ?? d.created_at) },
      { label: 'Assigned to', value: assigned || 'Nobody yet', muted: !assigned },
      { label: 'Description', value: d.description },
      ...(d.attachments.length > 0 ? [{ label: 'Files' }] : []),
    ]
  })
</script>
