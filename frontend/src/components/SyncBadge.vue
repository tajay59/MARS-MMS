<template>
  <v-btn
    :aria-label="uploadsLabel ?? 'All synced'"
    :class="failed ? 'text-warning' : (uploadsLabel ? 'text-primary' : 'text-success')"
    icon
    size="40"
    :to="{ name: 'sync' }"
    variant="text"
  >
    <v-icon :icon="uploadsLabel ? mdiCloudUploadOutline : mdiCloudCheckOutline" size="22" />
  </v-btn>
</template>

<script lang="ts" setup>
  import { mdiCloudCheckOutline, mdiCloudUploadOutline } from '@mdi/js'
  import { computed } from 'vue'
  import { uploadsLabel, uploadsOnTheirWay } from '@/features/visits/uploadQueues'

  // The sync badge (AFD §5.1). Photos and video on their way to a visit's board are the only thing
  // that waits on a device until offline visits arrive in Phase 5; the outbox adds its own count.
  const failed = computed(() => uploadsOnTheirWay.value.sending === 0 && uploadsOnTheirWay.value.failed > 0)
</script>
