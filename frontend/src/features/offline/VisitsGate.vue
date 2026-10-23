<template>
  <OfflineVisitPage v-if="showCopy && id" :id="id" :key="id" />
  <VisitsPage v-else />
</template>

<script lang="ts" setup>
  import { defineAsyncComponent } from 'vue'
  import OfflineVisitPage from './OfflineVisitPage.vue'
  import { useOfflineMode } from './useOfflineMode'

  // /visits/:id with no connection reads the prepared copy; the list is the Visits page.
  const VisitsPage = defineAsyncComponent(() => import('@/features/visits/VisitsPage.vue'))
  const { id, showCopy } = useOfflineMode()
</script>
