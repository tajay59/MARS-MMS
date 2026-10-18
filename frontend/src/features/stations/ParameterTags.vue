<template>
  <span aria-label="Measures" class="flex flex-wrap gap-1" role="list" translate="no">
    <span
      v-for="p in shown"
      :key="p"
      class="inline-flex h-5.5 items-center rounded-full bg-surface-100 px-2 font-mono text-xs text-surface-700"
      role="listitem"
    >{{ p }}</span>

    <span
      v-if="hidden > 0"
      :aria-label="`and ${hidden} more`"
      class="inline-flex h-5.5 items-center rounded-full px-1.5 text-xs text-surface-600 tabular-nums"
      role="listitem"
    >+{{ hidden }}</span>
  </span>
</template>

<script lang="ts" setup>
  import { computed } from 'vue'
  import { sortParameters } from './stations'

  // What a station measures, as short codes (AT, RH, RAIN) in the usual order. `max` keeps a
  // phone card short: a real station can measure 25 (W5-8).
  const props = defineProps<{ parameters: readonly string[], max?: number }>()

  const sorted = computed(() => sortParameters(props.parameters))
  const shown = computed(() => props.max ? sorted.value.slice(0, props.max) : sorted.value)
  const hidden = computed(() => sorted.value.length - shown.value.length)
</script>
