<template>
  <v-btn
    :aria-label="label"
    :class="attention || failed ? 'text-error' : (busy ? 'text-primary' : 'text-success')"
    icon
    size="40"
    :to="{ name: 'sync' }"
    variant="text"
  >
    <v-badge v-if="count > 0" color="primary" :content="count > 99 ? '99+' : count" floating>
      <v-icon :icon="mdiCloudUploadOutline" size="22" />
    </v-badge>

    <v-icon v-else :icon="attention || failed ? mdiCloudAlertOutline : mdiCloudCheckOutline" size="22" />
  </v-btn>
</template>

<script lang="ts" setup>
  import { mdiCloudAlertOutline, mdiCloudCheckOutline, mdiCloudUploadOutline } from '@mdi/js'
  import { computed } from 'vue'
  import { useSyncOverview } from '@/features/field/useSyncOverview'
  import { uploadsLabel, uploadsOnTheirWay } from '@/features/visits/uploadQueues'

  // The sync badge (AFD §5.1, OFF-6): what waits on the phone, counted from IndexedDB so it is right
  // with no signal and after a restart. Files going up to a visit that is not kept on the phone are
  // held in memory (`uploadQueues`) and add their own words.
  const { totals } = useSyncOverview()

  const count = computed(() => totals.value.changes + totals.value.files)
  const attention = computed(() => totals.value.attention > 0)
  const failed = computed(() => uploadsOnTheirWay.value.sending === 0 && uploadsOnTheirWay.value.failed > 0)
  const busy = computed(() => count.value > 0 || uploadsLabel.value !== null)
  const label = computed(() => {
    if (attention.value) {
      return totals.value.attention === 1 ? '1 thing needs your attention' : `${totals.value.attention} things need your attention`
    }
    if (count.value > 0) {
      return `${count.value} waiting to sync`
    }
    return uploadsLabel.value ?? 'All synced'
  })
</script>
