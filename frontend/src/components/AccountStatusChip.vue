<template>
  <span class="inline-flex h-6 items-center gap-1 rounded-full px-2.5 text-xs font-medium" :class="look.class">
    <v-icon :icon="look.icon" size="14" />{{ look.label }}
  </span>
</template>

<script lang="ts" setup>
  import type { UserStatus } from '@/api/models'
  import { mdiAccountClockOutline, mdiCancel, mdiCheck, mdiCloseCircleOutline, mdiEmailOutline } from '@mdi/js'
  import { computed } from 'vue'

  // Account status: green Active, amber Pending, red Rejected, grey Disabled (DBD "Other status
  // sets"). Invited uses the blue pair, as in the approved Users mock-up.
  const props = defineProps<{ status: string }>()

  const looks: Record<UserStatus, { label: string, icon: string, class: string }> = {
    active: { label: 'Active', icon: mdiCheck, class: 'bg-success-container text-on-success-container' },
    invited: { label: 'Invited', icon: mdiEmailOutline, class: 'bg-info-container text-on-info-container' },
    pending: { label: 'Pending', icon: mdiAccountClockOutline, class: 'bg-warning-container text-on-warning-container' },
    rejected: { label: 'Rejected', icon: mdiCloseCircleOutline, class: 'bg-error-container text-on-error-container' },
    disabled: { label: 'Disabled', icon: mdiCancel, class: 'bg-surface-200 text-surface-700' },
  }

  const look = computed(() => looks[props.status as UserStatus] ?? looks.disabled)
</script>
