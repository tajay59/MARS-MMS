<template>
  <span aria-label="Measures" class="flex flex-wrap gap-1" role="list">
    <span
      v-for="p in sorted"
      :key="p"
      class="inline-flex h-5.5 items-center rounded-full bg-surface-100 px-2 font-mono text-xs text-surface-700"
      role="listitem"
    >{{ p }}</span>
  </span>
</template>

<script lang="ts" setup>
  import { computed } from 'vue'
  import { sortParameters } from './stations'

  // What a station measures, as short codes (AT, RH, RAIN) in the usual order
  const props = defineProps<{ parameters: readonly string[] }>()

  const sorted = computed(() => sortParameters(props.parameters))
</script>
