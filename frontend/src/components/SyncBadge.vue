<template>
  <v-btn
    aria-label="All synced"
    class="text-success"
    icon
    size="40"
    :to="{ name: 'sync' }"
    variant="text"
  >
    <v-icon :icon="mdiCloudCheckOutline" size="22" />
  </v-btn>
</template>

<script lang="ts" setup>
  import { mdiCloudCheckOutline } from '@mdi/js'

  // The sync badge (AFD §5.1). Nothing is queued on a device until offline visits arrive in
  // Phase 5, so it always reads "All synced" for now; the waiting count comes with the outbox.
</script>
