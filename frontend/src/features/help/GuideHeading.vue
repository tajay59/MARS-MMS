<template>
  <h2 :id="id" class="m-0 flex items-baseline gap-3.5 text-balance font-heading text-[1.375rem] font-medium leading-snug text-surface-900 md:text-[1.625rem]">
    <span aria-hidden="true" class="font-mono text-[0.9375rem] font-medium text-primary">{{ number }}</span>{{ title }}
  </h2>
</template>

<script lang="ts" setup>
  // A numbered section heading in a guide; the number is the contents' order, so it is not read out twice
  defineProps<{ id: string, number: number, title: string }>()
</script>
