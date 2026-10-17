<template>
  <div class="flex flex-col gap-2">
    <div class="flex items-baseline justify-between gap-2">
      <label class="text-label text-surface-900" :for="id">{{ label }}</label>
      <slot name="aside" />
    </div>

    <slot />
  </div>
</template>

<script lang="ts" setup>
  // A label above its input, as in the DBD forms (labels never float inside the field).
  defineProps<{
    id: string
    label: string
  }>()
</script>
