<template>
  <OfflineVisitPage v-if="offline && id" :id="id" :key="id" />
  <VisitFieldPage v-else />
</template>

<script lang="ts" setup>
  import { defineAsyncComponent } from 'vue'
  import OfflineVisitPage from './OfflineVisitPage.vue'
  import { useOfflineMode } from './useOfflineMode'

  // A started visit on a phone, with no connection: the prepared copy, read only (W13-13).
  const VisitFieldPage = defineAsyncComponent(() => import('@/features/visits/field/VisitFieldPage.vue'))
  const { id, offline } = useOfflineMode()
</script>
