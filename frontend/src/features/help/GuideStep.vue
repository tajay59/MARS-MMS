<template>
  <li class="grid grid-cols-[2rem_1fr] gap-3 border-t border-surface-200 py-3 last:border-b">
    <span aria-hidden="true" class="flex size-6 items-center justify-center rounded-full bg-primary-50 font-mono text-[0.8125rem] font-medium text-primary">{{ n }}</span>
    <p class="m-0"><slot /></p>
  </li>
</template>

<script lang="ts" setup>
  // One numbered step in a guide; the list's own order is what a screen reader announces
  defineProps<{ n: number }>()
</script>
