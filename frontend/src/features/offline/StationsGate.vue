<template>
  <OfflineStationPage v-if="showCopy && id" :id="id" :key="id" />
  <StationsPage v-else />
</template>

<script lang="ts" setup>
  import { defineAsyncComponent } from 'vue'
  import OfflineStationPage from './OfflineStationPage.vue'
  import { useOfflineMode } from './useOfflineMode'

  // /stations/:id with no connection reads the prepared copy; everything else is the Stations page.
  const StationsPage = defineAsyncComponent(() => import('@/features/stations/StationsPage.vue'))
  const { id, showCopy } = useOfflineMode()
</script>
