<template>
  <ul aria-label="Open requests by status" class="m-0 flex list-none flex-col gap-1.5 p-0">
    <li v-for="row in counts" :key="row.status" class="flex items-center gap-3">
      <span class="w-28 shrink-0 text-right text-sm text-surface-600">{{ lookOf(row.status).label }}</span>

      <span aria-hidden="true" class="flex h-[18px] min-w-0 grow items-center">
        <span class="h-full" :class="barFill[row.status] ?? 'bg-surface-500'" :style="{ width: widths[row.status] + '%' }" />
      </span>

      <span class="w-8 shrink-0 text-sm font-semibold tabular-nums text-surface-900">{{ row.count }}</span>
    </li>
  </ul>
</template>

<script lang="ts" setup>
  import { computed } from 'vue'
  import { lookOf } from '@/features/requests/requests'
  import { barFill, barWidths } from './dashboard'

  // Requests by status as bars in the status colours (DBD "Charts"): a number before a chart, one
  // hue per status in the order of the status table, every bar labelled with its count. Plain
  // elements, so a screen reader reads a list and nothing is loaded for it.
  const props = defineProps<{ counts: readonly { status: string, count: number }[] }>()

  const widths = computed(() => barWidths(props.counts))
</script>
