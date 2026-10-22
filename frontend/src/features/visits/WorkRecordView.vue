<template>
  <div class="flex flex-col gap-5">
    <p v-if="work.version === 0" class="m-0 text-sm text-surface-600">Nothing has been recorded for this station yet.</p>

    <template v-else>
      <p class="m-0 flex items-center gap-2 text-xs text-surface-700">
        <v-icon class="shrink-0 text-primary" :icon="mdiInformationOutline" size="16" />
        <span>Work record, version {{ work.version }}.<template v-if="work.updated_at"> Saved <template v-if="savedBy">by {{ savedBy }}, </template>{{ formatWhen(work.updated_at, zone) }}.</template></span>
      </p>

      <section v-if="work.condition_on_arrival?.status || work.condition_on_arrival?.notes" aria-labelledby="wr-arrival" class="flex flex-col gap-1.5">
        <h3 id="wr-arrival" class="m-0 text-sm font-semibold text-surface-900">Condition on arrival</h3>

        <div class="flex flex-wrap items-center gap-2 text-sm">
          <span v-if="work.condition_on_arrival.status" class="inline-flex h-6 items-center rounded-md bg-surface-100 px-2 text-xs font-medium text-surface-900">{{ CONDITION_LABEL[work.condition_on_arrival.status] }}</span>
          <span v-if="work.condition_on_arrival.notes" class="text-surface-700">{{ work.condition_on_arrival.notes }}</span>
        </div>
      </section>

      <section v-if="work.checklist.length > 0" aria-labelledby="wr-checklist" class="flex flex-col gap-1.5">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h3 id="wr-checklist" class="m-0 text-sm font-semibold text-surface-900">Checklist</h3>
          <span class="text-xs text-surface-600">{{ checklistSummary(work.checklist) }}</span>
        </div>

        <div v-for="(group, at) in groups" :key="at" class="flex flex-col">
          <h4 v-if="group.title" class="m-0 mt-2 text-xs font-semibold tracking-wide text-surface-700">{{ group.title }}</h4>

          <ul class="m-0 flex list-none flex-col p-0">
            <li v-for="row in group.rows" :key="row.item_id" class="grid grid-cols-[1fr_auto] items-start gap-x-3 gap-y-1 border-t border-surface-200 py-2 first:border-t-0">
              <span class="text-sm text-surface-900">{{ row.label }}</span>
              <span class="inline-flex h-6 items-center rounded-md px-2 text-xs font-semibold" :class="chip(row.result)">{{ row.result ? RESULT_LABEL[row.result] : 'Not answered' }}</span>
              <span v-if="row.note" class="col-span-2 text-[13px] text-surface-700">{{ row.note }}</span>
            </li>
          </ul>
        </div>
      </section>

      <section v-if="sentences.length > 0" aria-labelledby="wr-actions" class="flex flex-col gap-1.5">
        <h3 id="wr-actions" class="m-0 text-sm font-semibold text-surface-900">Sensor actions</h3>

        <ul class="m-0 flex list-none flex-col p-0">
          <li v-for="s in sentences" :key="s.id" class="grid grid-cols-[24px_1fr_auto] items-start gap-x-2.5 border-t border-surface-200 py-2.5 first:border-t-0">
            <span class="flex size-6 items-center justify-center rounded-full bg-primary-100 text-primary-700"><v-icon :icon="icons.sensor" size="14" /></span>

            <div class="min-w-0 text-sm text-surface-900">
              <span :aria-label="plain(s)">
                <template v-for="(part, i) in s.segments" :key="i"><span v-if="part.mono" class="font-mono" translate="no">{{ part.text }}</span><b v-else-if="part.bold" class="font-semibold">{{ part.text }}</b><template v-else>{{ part.text }}</template></template>
              </span>

              <div v-if="s.detail" class="mt-0.5 text-[13px] text-surface-700">{{ s.detail }}</div>
            </div>

            <span v-if="s.changesInventory" class="inline-flex items-center gap-1 whitespace-nowrap text-xs font-semibold" :class="visitEnded ? 'text-primary' : 'text-surface-700'">
              <v-icon v-if="visitEnded" :icon="mdiCheck" size="14" />
              {{ visitEnded ? 'In the inventory' : 'Draft' }}
            </span>
          </li>
        </ul>
      </section>

      <section v-if="work.config_versions.length > 0" aria-labelledby="wr-config" class="flex flex-col gap-1.5">
        <h3 id="wr-config" class="m-0 text-sm font-semibold text-surface-900">Configuration</h3>

        <ul class="m-0 flex list-none flex-col gap-1 p-0 text-sm text-surface-900">
          <li v-for="(version, at) in work.config_versions" :key="String(version.id ?? at)">
            {{ filesIn(version) }}<template v-if="version.notes"> · {{ version.notes }}</template>
          </li>
        </ul>
      </section>

      <div class="grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-2">
        <section aria-labelledby="wr-parts" class="flex flex-col gap-1.5">
          <h3 id="wr-parts" class="m-0 text-sm font-semibold text-surface-900">Parts used</h3>
          <p v-if="work.parts_used.length === 0" class="m-0 text-sm text-surface-600">None</p>

          <ul v-else class="m-0 flex list-none flex-col gap-0.5 p-0 text-sm text-surface-900">
            <li v-for="(part, at) in work.parts_used" :key="String(part.id ?? at)">{{ part.quantity }} × {{ part.description }}</li>
          </ul>
        </section>

        <section aria-labelledby="wr-data" class="flex flex-col gap-1.5">
          <h3 id="wr-data" class="m-0 text-sm font-semibold text-surface-900">Data downloaded</h3>
          <p class="m-0 text-sm text-surface-900">{{ downloadedSentence(work.data_downloaded, iso => formatDate(iso, zone)) }}</p>
        </section>

        <section v-if="work.condition_on_departure?.status || work.condition_on_departure?.notes" aria-labelledby="wr-departure" class="flex flex-col gap-1.5">
          <h3 id="wr-departure" class="m-0 text-sm font-semibold text-surface-900">Condition on departure</h3>

          <div class="flex flex-wrap items-center gap-2 text-sm">
            <span v-if="work.condition_on_departure.status" class="inline-flex h-6 items-center rounded-md bg-surface-100 px-2 text-xs font-medium text-surface-900">{{ CONDITION_LABEL[work.condition_on_departure.status] }}</span>
            <span v-if="work.condition_on_departure.notes" class="text-surface-700">{{ work.condition_on_departure.notes }}</span>
          </div>
        </section>

        <section aria-labelledby="wr-issues" class="flex flex-col gap-1.5">
          <h3 id="wr-issues" class="m-0 text-sm font-semibold text-surface-900">Issues found</h3>
          <p v-if="work.issues_found.length === 0" class="m-0 text-sm text-surface-600">None</p>

          <ul v-else class="m-0 flex list-none flex-col gap-1 p-0 text-sm text-surface-900">
            <li v-for="(issue, at) in work.issues_found" :key="String(issue.id ?? at)" class="flex flex-wrap items-center gap-2">
              {{ issue.description }}
              <span class="inline-flex h-5 items-center rounded-md bg-surface-100 px-1.5 text-xs font-medium text-surface-900">{{ severityLabel(issue.severity) }}</span>
            </li>
          </ul>
        </section>
      </div>

      <section v-if="work.notes" aria-labelledby="wr-notes" class="flex flex-col gap-1.5">
        <h3 id="wr-notes" class="m-0 text-sm font-semibold text-surface-900">Notes</h3>
        <p class="m-0 whitespace-pre-line text-sm text-surface-900">{{ work.notes }}</p>
      </section>
    </template>
  </div>
</template>

<script lang="ts" setup>
  import type { WorkOut } from '@/api/models'
  import { mdiCheck, mdiInformationOutline } from '@mdi/js'
  import { computed } from 'vue'
  import { formatDate } from '@/app/format'
  import { icons } from '@/app/theme/icons'
  import { formatWhen } from './visits'
  import { actionSentences, checklistGroups, checklistSummary, CONDITION_LABEL, downloadedSentence, plain, RESULT_LABEL, severityLabel } from './work'

  // A station's work record, read only (PRD VIS-7; board "W11 screens" 3). The owner fills it in
  // on the phone in W12; staff read it here. Sensor actions read as sentences, and say whether
  // they are in the inventory yet (they are applied when the visit ends). Clients never get it.
  const props = defineProps<{
    work: WorkOut
    visitEnded: boolean
    zone?: string | null
    /** Who saved it, when that is known (the owner); null otherwise. */
    savedBy?: string | null
  }>()

  const groups = computed(() => checklistGroups(props.work.checklist))
  const sentences = computed(() => actionSentences(props.work))

  function chip (result: string | null): string {
    switch (result) {
      case 'ok': {
        return 'bg-primary-100 text-primary-700'
      }
      case 'fixed': {
        return 'border border-surface-300 bg-surface-100 text-surface-900'
      }
      case 'issue': {
        return 'bg-error-container text-on-error-container'
      }
      default: {
        return 'border border-surface-300 text-surface-600'
      }
    }
  }

  function filesIn (version: Record<string, unknown>): string {
    const n = Array.isArray(version.files) ? version.files.length : 0
    return `${n} configuration ${n === 1 ? 'file' : 'files'}`
  }
</script>
