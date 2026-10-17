<template>
  <PageBody :title="isClient ? 'Page not found' : undefined">
    <v-card class="flex max-w-xl flex-col items-start gap-3 border border-surface-200 p-6">
      <v-icon class="text-surface-500" :icon="mdiMapMarkerQuestionOutline" size="32" />
      <h2 class="m-0 text-h3 text-surface-900">We can’t find that page</h2>
      <p class="m-0 text-surface-600">The link may be wrong, or the page isn’t one you can open.</p>
      <v-btn class="text-primary" :to="{ name: 'dashboard' }" variant="outlined">Go to the dashboard</v-btn>
    </v-card>
  </PageBody>
</template>

<script lang="ts" setup>
  import { mdiMapMarkerQuestionOutline } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import PageBody from '@/components/PageBody.vue'
  import { useSessionStore } from '@/stores/session'

  // Missing records, other organizations' records and pages a role can't use all look the same
  // (AFD §5.2, ADR-16).
  const { isClient } = storeToRefs(useSessionStore())
</script>
