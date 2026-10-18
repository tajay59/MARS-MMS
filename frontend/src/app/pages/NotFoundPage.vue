<template>
  <PageBody>
    <div class="flex max-w-xl flex-col items-start gap-3">
      <v-icon class="text-surface-500" :icon="mdiMapMarkerQuestionOutline" size="32" />
      <h2 class="m-0 text-h3 text-surface-900">We can’t find that page</h2>
      <p class="m-0 text-surface-600">The link may be wrong, or the page isn’t one you can open.</p>
      <v-btn class="text-primary" :to="{ name: 'dashboard' }" variant="outlined">Go to the dashboard</v-btn>
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import { mdiMapMarkerQuestionOutline } from '@mdi/js'
  import PageBody from '@/components/PageBody.vue'

  // Missing records, other organizations' records and pages a role can't use all look the same
  // (AFD §5.2, ADR-16).
</script>
