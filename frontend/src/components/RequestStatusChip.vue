<template>
  <span class="inline-flex h-6 shrink-0 items-center gap-1 whitespace-nowrap rounded-full pl-2 pr-2.5 text-xs font-medium" :class="look.chip">
    <v-icon :icon="look.icon" size="14" />{{ look.label }}
  </span>
</template>

<script lang="ts" setup>
  import { computed } from 'vue'
  import { lookOf } from '@/features/requests/requests'

  // Request status: icon, word and colour together (DBD Status colours), never colour alone
  const props = defineProps<{ status: string }>()

  const look = computed(() => lookOf(props.status))
</script>
