<template>
  <span
    class="inline-flex h-6 items-center gap-1.25 whitespace-nowrap rounded-full px-2.5 text-xs font-medium"
    :class="doc.client_visible ? 'bg-primary-100 text-primary-800' : 'bg-surface-100 text-surface-700'"
  >
    <v-icon :icon="doc.client_visible ? mdiEyeOutline : mdiLockOutline" size="14" />
    {{ doc.client_visible ? `Shown to ${orgName ?? 'the owner'}` : 'Staff only' }}
  </span>
</template>

<script lang="ts" setup>
  import type { DocumentOut } from '@/api/models'
  import { mdiEyeOutline, mdiLockOutline } from '@mdi/js'

  // Who can see a document (DOC-4): staff only until someone turns it on
  defineProps<{
    doc: Pick<DocumentOut, 'client_visible'>
    orgName?: string | null
  }>()
</script>
