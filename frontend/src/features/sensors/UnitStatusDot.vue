<template>
  <span aria-hidden="true" class="inline-block size-2 shrink-0 rounded-full" :class="look" />
</template>

<script lang="ts" setup>
  import { computed } from 'vue'

  // The dot beside a unit's status. Neutral and brand tones only: the reserved status colours
  // belong to requests and stations, and calibration has its own chip.
  const props = defineProps<{
    status: string
  }>()

  const looks: Record<string, string> = {
    installed: 'bg-primary',
    in_stock: 'bg-surface-500',
    in_repair: 'bg-surface-900',
    retired: 'border border-surface-500 bg-transparent',
  }

  const look = computed(() => looks[props.status] ?? 'bg-surface-400')
</script>
