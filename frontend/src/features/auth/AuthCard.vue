<template>
  <v-card class="flex flex-col gap-6 border border-surface-200 p-6 md:p-8">
    <div class="flex flex-col gap-2">
      <h1 class="m-0 text-2xl font-semibold leading-8 tracking-[-0.01em] text-surface-900 md:text-display">{{ title }}</h1>
      <p v-if="lead" class="m-0 text-body text-surface-900">{{ lead }}</p>
    </div>

    <slot />
  </v-card>
</template>

<script lang="ts" setup>
  // The form card on the split panel: max 440 px, white (DBD public pages).
  defineProps<{ title: string, lead?: string }>()
</script>
