<template>
  <div class="flex min-w-0 flex-col gap-4">
    <div class="flex items-start justify-between gap-3">
      <h2 :id="headingId" class="m-0 text-h2 text-surface-900">Record {{ record.seq.toLocaleString('en-GB') }}</h2>

      <v-btn
        aria-label="Close the record"
        icon
        size="36"
        variant="text"
        @click="emit('close')"
      >
        <v-icon :icon="mdiClose" />
      </v-btn>
    </div>

    <div>
      <span class="inline-flex h-6.5 items-center rounded-full bg-surface-100 px-2.5 font-mono text-xs text-surface-800" translate="no">{{ record.action }}</span>
      <p class="m-0 mt-1.5 text-sm text-surface-700">{{ record.actor.name ?? 'System' }} {{ record.summary }}.</p>
    </div>

    <dl class="m-0 grid grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-sm">
      <dt class="text-surface-600">When</dt>
      <dd class="m-0 break-words">{{ formatDateTime(record.at) }}</dd>
      <dt class="text-surface-600">Who</dt>
      <dd class="m-0 break-words">{{ record.actor.name ?? 'System' }}, {{ roleLabel(record.actor.roles) }}</dd>

      <template v-if="record.actor.ip || record.actor.user_agent">
        <dt class="text-surface-600">From</dt>
        <dd class="m-0 break-words">{{ [record.actor.ip, record.actor.user_agent].filter(Boolean).join(', ') }}</dd>
      </template>

      <dt class="text-surface-600">Resource</dt>
      <dd class="m-0 break-words">{{ resourceLabel(record.resource?.type) }} <span class="font-mono text-xs" translate="no">{{ record.resource?.id }}</span></dd>
      <dt class="text-surface-600">Organization</dt>
      <dd class="m-0 break-words font-mono text-xs" translate="no">{{ record.org_id ?? '—' }}</dd>
    </dl>

    <template v-if="record.changes.length > 0">
      <v-divider />
      <h3 class="m-0 text-h3 text-surface-900">What changed</h3>

      <div class="overflow-x-auto">
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="text-left text-xs text-surface-600">
              <th class="py-1.5 pr-2 font-semibold" scope="col">Field</th>
              <th class="px-2 py-1.5 font-semibold" scope="col">Before</th>
              <th class="py-1.5 pl-2 font-semibold" scope="col">After</th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="c in record.changes" :key="c.field" class="border-t border-surface-200 align-top">
              <th class="py-2 pr-2 text-left font-mono text-xs font-normal" scope="row" translate="no">{{ c.field }}</th>
              <td class="break-words px-2 py-2">{{ showValue(c.before) }}</td>
              <td class="break-words py-2 pl-2">{{ showValue(c.after) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <v-divider />
    <h3 class="m-0 text-h3 text-surface-900">Chain</h3>

    <dl class="m-0 grid grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-sm">
      <dt class="text-surface-600">Position</dt>
      <dd class="m-0 tabular-nums">{{ record.seq.toLocaleString('en-GB') }}</dd>
      <dt class="text-surface-600">Hash</dt>
      <dd class="m-0 break-all font-mono text-xs" translate="no">{{ record.hash.slice(0, 16) }}…</dd>
      <dt class="text-surface-600">Before it</dt>
      <dd class="m-0 break-all font-mono text-xs" translate="no">{{ record.prev_hash.slice(0, 16) }}…</dd>

      <template v-if="record.correlation_id">
        <dt class="text-surface-600">Trace</dt>
        <dd class="m-0 break-all font-mono text-xs" translate="no">{{ record.correlation_id }}</dd>
      </template>
    </dl>
  </div>
</template>

<script lang="ts" setup>
  import type { AuditRecord } from '@/api/models'
  import { mdiClose } from '@mdi/js'
  import { formatDateTime } from '@/app/format'
  import { resourceLabel, roleLabel, showValue } from './audit'

  // One audit record in full (admins only): who, what, the values before and after, and its place
  // in the chain (AUD-2, AUD-4). The heading's id is `headingId`, for the dialog that holds it.
  defineProps<{ record: AuditRecord, headingId: string }>()
  const emit = defineEmits<{ close: [] }>()
</script>
