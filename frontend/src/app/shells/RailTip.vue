<template>
  <!--
    A rail tooltip: shown while its `group` parent is hovered or has keyboard focus. CSS only, so
    it works without a pointer, and screen readers get the hint from the parent's aria-describedby.
  -->
  <span
    aria-hidden="true"
    class="pointer-events-none absolute left-full top-1/2 z-[1006] ml-3 flex -translate-y-1/2 flex-col gap-0.5 whitespace-nowrap rounded-md bg-surface-900 px-3 py-2 text-left text-surface-0 opacity-0 shadow-lg transition-opacity duration-100 group-hover:opacity-100 group-focus-visible:opacity-100 group-has-[:focus-visible]:opacity-100 motion-reduce:transition-none"
  >
    <span class="text-sm font-semibold leading-4">{{ label }}</span>
    <span :id="hintId" class="text-xs leading-4">{{ hint }}</span>
  </span>
</template>

<script lang="ts" setup>
  defineProps<{ label: string, hint: string, hintId: string }>()
</script>
