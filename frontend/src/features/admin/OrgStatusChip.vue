<template>
  <span
    class="inline-flex h-6 items-center gap-1 rounded-full px-2.5 text-xs font-medium"
    :class="active ? 'bg-success-container text-on-success-container' : 'bg-surface-200 text-surface-700'"
  >
    <v-icon :icon="active ? mdiCheck : mdiCancel" size="14" />{{ active ? 'Active' : 'Inactive' }}
  </span>
</template>

<script lang="ts" setup>
  import { mdiCancel, mdiCheck } from '@mdi/js'
  import { computed } from 'vue'

  // An organization's status (ORG-4): green Active, grey Inactive, as the account chips
  const props = defineProps<{ status: string }>()
  const active = computed(() => props.status === 'active')
</script>
