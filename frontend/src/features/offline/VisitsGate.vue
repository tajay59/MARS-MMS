<template>
  <template v-if="showCopy && id">
    <VisitFieldPage v-if="kept" :key="id" />
    <OfflineVisitPage v-else-if="kept === false" :id="id" :key="id" />
  </template>

  <VisitsPage v-else />
</template>

<script lang="ts" setup>
  import { defineAsyncComponent } from 'vue'
  import OfflineVisitPage from './OfflineVisitPage.vue'
  import { useOfflineMode } from './useOfflineMode'

  // /visits/:id with no connection: a visit prepared on this phone opens the field page, which works
  // from the phone's own copy; any other says it is not here. The list is the Visits page.
  const VisitsPage = defineAsyncComponent(() => import('@/features/visits/VisitsPage.vue'))
  const VisitFieldPage = defineAsyncComponent(() => import('@/features/visits/field/VisitFieldPage.vue'))
  const { id, kept, showCopy } = useOfflineMode()
</script>
