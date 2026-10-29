<template>
  <PageBody subtitle="Every change is recorded and chained to the one before it. Nobody can edit or delete a record here." title="Audit log">
    <template #actions>
      <v-btn
        :disabled="integrity.starting.value || running"
        :loading="integrity.starting.value"
        :prepend-icon="mdiShieldCheckOutline"
        variant="outlined"
        @click="integrity.start()"
      >Check integrity</v-btn>

      <v-btn
        :disabled="total === 0 || over"
        :loading="exporting"
        :prepend-icon="mdiDownloadOutline"
        variant="tonal"
        @click="exportNow"
      >Export CSV</v-btn>
    </template>

    <PaneContent pin>
      <form class="flex flex-col gap-3 px-3" role="search" @submit.prevent>
        <div class="flex items-center justify-between">
          <h3 class="m-0 text-h3 text-surface-900">Filters</h3>
          <v-btn :disabled="activeCount(filters) === 0" size="small" variant="text" @click="clear">Clear</v-btn>
        </div>

        <FormField :id="`${uid}-actor`" label="Who did it">
          <v-text-field
            :id="`${uid}-actor`"
            autocomplete="off"
            clearable
            density="comfortable"
            flat
            hide-details
            :model-value="filters.actor"
            name="actor"
            placeholder="Name or user id"
            :prepend-inner-icon="mdiMagnify"
            spellcheck="false"
            variant="solo-inverted"
            @update:model-value="set({ actor: $event ?? '' })"
          />
        </FormField>

        <FormField :id="`${uid}-action`" label="Action">
          <v-text-field
            :id="`${uid}-action`"
            autocomplete="off"
            clearable
            density="comfortable"
            flat
            hide-details
            :model-value="filters.action"
            name="action"
            placeholder="request.approved"
            spellcheck="false"
            variant="solo-inverted"
            @update:model-value="set({ action: $event ?? '' })"
          />
        </FormField>

        <FormField :id="`${uid}-rtype`" label="Resource">
          <v-select
            :id="`${uid}-rtype`"
            density="comfortable"
            flat
            hide-details
            item-title="label"
            item-value="value"
            :items="RESOURCE_TYPES"
            :model-value="filters.resourceType"
            variant="solo-inverted"
            @update:model-value="set({ resourceType: $event ?? '' })"
          />
        </FormField>

        <FormField :id="`${uid}-org`" label="Organization">
          <v-select
            :id="`${uid}-org`"
            clearable
            density="comfortable"
            flat
            hide-details
            item-title="name"
            item-value="id"
            :items="orgs"
            :model-value="filters.org"
            placeholder="All organizations"
            variant="solo-inverted"
            @update:model-value="set({ org: $event ?? null })"
          />
        </FormField>

        <div class="grid grid-cols-2 gap-3">
          <FormField :id="`${uid}-from`" label="From">
            <v-text-field
              :id="`${uid}-from`"
              density="comfortable"
              flat
              hide-details
              :model-value="filters.from"
              name="from"
              type="date"
              variant="solo-inverted"
              @update:model-value="set({ from: $event ?? '' })"
            />
          </FormField>

          <FormField :id="`${uid}-to`" label="To">
            <v-text-field
              :id="`${uid}-to`"
              density="comfortable"
              flat
              hide-details
              :model-value="filters.to"
              name="to"
              type="date"
              variant="solo-inverted"
              @update:model-value="set({ to: $event ?? '' })"
            />
          </FormField>
        </div>

        <p class="m-0 text-xs text-surface-600">Days are your days. Times are shown in your time zone and stored in UTC.</p>
      </form>
    </PaneContent>

    <div class="flex min-h-0 gap-0">
      <div class="flex min-w-0 grow flex-col gap-4">
        <FeedbackBanner v-if="checkLook" :icon="checkLook.tone === 'success' ? mdiShieldCheckOutline : undefined" :type="checkLook.tone">
          <p class="m-0"><span class="font-semibold">{{ checkLook.title }}</span> {{ checkLook.text }}</p>

          <v-progress-linear
            v-if="checkLook.running"
            class="mt-2"
            color="primary"
            height="4"
            indeterminate
            rounded
          />
        </FeedbackBanner>

        <FeedbackBanner v-if="integrity.problem.value" type="error">{{ integrity.problem.value }}</FeedbackBanner>

        <FeedbackBanner v-if="over" type="warning">
          <span class="font-semibold">More than {{ EXPORT_LIMIT.toLocaleString('en-GB') }} records match.</span> Narrow the dates or the filters, then export again.
        </FeedbackBanner>

        <FeedbackBanner v-if="exported" :icon="mdiCheck" type="success">{{ exported }}</FeedbackBanner>
        <FeedbackBanner v-if="exportProblem" type="error">{{ exportProblem }}</FeedbackBanner>

        <FeedbackBanner v-if="problem" type="error">
          <div class="flex flex-wrap items-center gap-3">
            <span class="grow">{{ problem }}</span>
            <v-btn size="small" variant="text" @click="reload">Try again</v-btn>
          </div>
        </FeedbackBanner>

        <v-skeleton-loader v-else-if="loading" type="table-row, table-row, table-row, table-row" />

        <div v-else-if="items.length === 0" class="flex flex-col items-start gap-1.5 rounded-card bg-surface-50 p-5">
          <p class="m-0 font-semibold text-surface-900">No records match these filters.</p>
          <p class="m-0 text-sm text-surface-600">Try a wider range of dates, or clear a filter.</p>
          <v-btn size="small" variant="outlined" @click="clear">Clear filters</v-btn>
        </div>

        <template v-else>
          <p class="m-0 text-sm text-surface-600" role="status"><span class="font-semibold tabular-nums text-surface-900">{{ total.toLocaleString('en-GB') }}{{ over ? '+' : '' }}</span> records match, newest first</p>

          <div aria-label="Audit records" class="overflow-x-auto" role="region" tabindex="0">
            <table class="w-full border-collapse text-sm">
              <thead>
                <tr class="text-left text-xs text-surface-600">
                  <th class="py-2 pr-3 font-semibold" scope="col">When</th>
                  <th class="px-3 py-2 font-semibold" scope="col">Who</th>
                  <th class="px-3 py-2 font-semibold" scope="col">Action</th>
                  <th class="px-3 py-2 font-semibold" scope="col">Resource</th>
                </tr>
              </thead>

              <tbody>
                <tr v-for="r in items" :key="r.seq" class="relative border-t border-surface-200 hover:bg-surface-50" :class="r.seq === selectedSeq ? 'bg-primary-50 dark:bg-primary-900' : ''">
                  <td class="whitespace-nowrap py-2 pr-3 tabular-nums">
                    <button
                      :aria-pressed="r.seq === selectedSeq"
                      class="text-left text-surface-900 after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-primary"
                      type="button"
                      @click="select(r.seq)"
                    >{{ formatDateTime(r.at) }}<span class="sr-only"> (record {{ r.seq }})</span></button>
                  </td>

                  <td class="px-3 py-2"><span class="block font-medium text-surface-900">{{ r.actor.name ?? 'System' }}</span><span class="block text-xs text-surface-600">{{ roleLabel(r.actor.roles) }}</span></td>
                  <td class="px-3 py-2 font-mono text-xs" translate="no">{{ r.action }}</td>
                  <td class="px-3 py-2"><span class="block">{{ resourceLabel(r.resource?.type) }}</span><span class="block font-mono text-xs text-surface-600" translate="no">{{ shortId(r.resource?.id ?? '') }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-if="next !== null" class="flex justify-center">
            <v-btn :loading="loadingMore" variant="outlined" @click="more">Show more</v-btn>
          </div>
        </template>
      </div>

      <!-- The record: beside the table on a wide screen, a dialog or a sheet otherwise -->
      <aside v-if="selected && lgAndUp" aria-label="Record" class="ml-6 w-107.5 shrink-0 border-l border-surface-200 pl-6">
        <AuditRecordView :heading-id="`${uid}-record`" :record="selected" @close="select(null)" />
      </aside>
    </div>

    <ModalSheet v-if="!lgAndUp" v-model="sheetOpen" :labelledby="`${uid}-record`" max-width="520">
      <AuditRecordView v-if="selected" :heading-id="`${uid}-record`" :record="selected" @close="select(null)" />
    </ModalSheet>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { Filters } from './audit'
  import { mdiCheck, mdiDownloadOutline, mdiMagnify, mdiShieldCheckOutline } from '@mdi/js'
  import { computed, onMounted, ref, useId } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { formatDateTime } from '@/app/format'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import { useSessionStore } from '@/stores/session'
  import { useStationDirectory } from '@/stores/stationDirectory'
  import { activeCount, EMPTY_FILTERS, filtersFrom, lookOfCheck, queryFrom, RESOURCE_TYPES, resourceLabel, roleLabel, shortId } from './audit'
  import AuditRecordView from './AuditRecordView.vue'
  import { saveExport, useAuditLog, useIntegrity } from './useAuditLog'

  // The audit log (PRD AUD-4, AUD-5; AFD J10; admins only): search, read a record in full, export
  // the search as CSV and check the chain. The filters and the open record are in the address.
  // It needs a connection and keeps nothing on the device (OFF-10).
  const EXPORT_LIMIT = 50_000
  const uid = useId()
  const route = useRoute()
  const router = useRouter()
  const { lgAndUp } = useDisplay()
  const session = useSessionStore()
  const directory = useStationDirectory()

  const filters = computed<Filters>(() => filtersFrom(route.query))
  const selectedSeq = computed(() => {
    const value = route.query.seq
    return typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : null
  })

  const { items, total, over, next, loading, loadingMore, problem, more, reload } = useAuditLog(() => filters.value)
  const selected = computed(() => items.value.find(r => r.seq === selectedSeq.value) ?? null)
  const sheetOpen = computed({
    get: () => selected.value !== null && !lgAndUp.value,
    set: value => {
      if (!value) {
        select(null)
      }
    },
  })

  const integrity = useIntegrity()
  const checkLook = computed(() => integrity.check.value ? lookOfCheck(integrity.check.value) : null)
  const running = computed(() => checkLook.value?.running ?? false)

  const orgs = computed(() => [...new Map(directory.stations.map(s => [s.owner_org_id, { id: s.owner_org_id, name: s.owner_org_name ?? 'Organization' }])).values()]
    .toSorted((a, b) => a.name.localeCompare(b.name)))

  function set (change: Partial<Filters>): void {
    void router.replace({ query: { ...queryFrom({ ...filters.value, ...change }), seq: undefined } })
  }

  function clear (): void {
    void router.replace({ query: { ...queryFrom(EMPTY_FILTERS) } })
  }

  function select (seq: number | null): void {
    void router.replace({ query: { ...route.query, seq: seq === null ? undefined : String(seq) } })
  }

  const exporting = ref(false)
  const exported = ref<string | null>(null)
  const exportProblem = ref<string | null>(null)

  async function exportNow (): Promise<void> {
    exporting.value = true
    exported.value = null
    exportProblem.value = null
    const result = await saveExport(filters.value)
    exporting.value = false
    if (result.ok) {
      exported.value = `Exported ${total.value.toLocaleString('en-GB')} records. This export is recorded in the audit log.`
    } else {
      exportProblem.value = result.message
    }
  }

  onMounted(() => {
    void integrity.latest()
    if (session.user) {
      void directory.load(session.user.id)
    }
  })
</script>
