<template>
  <template v-if="offline && id">
    <VisitFieldPage v-if="kept" :key="id" />
    <OfflineVisitPage v-else-if="kept === false" :id="id" :key="id" />
  </template>

  <VisitFieldPage v-else />
</template>

<script lang="ts" setup>
  import { defineAsyncComponent } from 'vue'
  import OfflineVisitPage from './OfflineVisitPage.vue'
  import { useOfflineMode } from './useOfflineMode'

  // A started visit on a phone: the field page. With no connection it needs the visit to be prepared
  // on this phone (it works from the phone's own copy); otherwise it says the visit is not here.
  const VisitFieldPage = defineAsyncComponent(() => import('@/features/visits/field/VisitFieldPage.vue'))
  const { id, kept, offline } = useOfflineMode()
</script>
