<template>
  <!-- Client pages carry their own h1; staff pages have it in the top bar (DBD shells). -->
  <div :class="isClient ? '' : 'mx-auto w-full max-w-[1280px] p-4 md:p-6'">
    <div v-if="isClient && title" class="mb-8 flex flex-wrap items-center gap-4">
      <div class="grow">
        <h1 class="m-0 text-display tracking-[-0.01em] text-surface-900">{{ title }}</h1>
        <p v-if="subtitle" class="m-0 text-surface-600">{{ subtitle }}</p>
      </div>

      <slot name="actions" />
    </div>

    <div v-else-if="$slots.actions || subtitle" class="mb-6 flex flex-wrap items-center gap-4">
      <p v-if="subtitle" class="m-0 grow text-surface-600">{{ subtitle }}</p>
      <slot name="actions" />
    </div>

    <slot />
  </div>
</template>

<script lang="ts" setup>
  import { storeToRefs } from 'pinia'
  import { useSessionStore } from '@/stores/session'

  defineProps<{ title?: string, subtitle?: string }>()
  const { isClient } = storeToRefs(useSessionStore())
</script>
