<template>
  <ul aria-label="Reports awaiting finalization" class="m-0 flex list-none flex-col p-0">
    <li v-for="report in reports" :key="report.report_id" class="relative flex items-center gap-3 border-b border-surface-200 py-2.5 last:border-b-0">
      <v-icon aria-hidden="true" class="text-surface-600" :icon="mdiFileDocumentOutline" size="20" />

      <span class="flex min-w-0 grow flex-col">
        <component
          :is="staff ? 'router-link' : 'span'"
          class="truncate font-medium text-surface-900 no-underline hover:underline after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-primary"
          v-bind="staff ? { to: { name: 'visit-report', params: { id: report.report_id } } } : {}"
        ><span class="font-mono" translate="no">{{ report.number }}</span> · v{{ report.version }}</component>

        <span class="truncate text-xs text-surface-600">
          <template v-if="report.station_codes.length > 0"><span class="font-mono" translate="no">{{ report.station_codes.join(', ') }}</span></template>
          <template v-if="report.lead_name"> · lead {{ report.lead_name }}</template>
        </span>
      </span>

      <span class="shrink-0 rounded-full bg-surface-100 px-2.5 py-0.5 text-xs font-medium text-surface-700">Draft · {{ waiting(report.age_days) }}</span>
    </li>
  </ul>
</template>

<script lang="ts" setup>
  import type { AwaitingReport } from '@/api/models'
  import { mdiFileDocumentOutline } from '@mdi/js'
  import { waiting } from './dashboard'

  // Draft visit reports not yet final, oldest first. Staff open the report to sign it; the
  // Viewer only reads the row.
  defineProps<{ reports: readonly AwaitingReport[], staff: boolean }>()
</script>
