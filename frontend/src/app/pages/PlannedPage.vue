<template>
  <PageBody :title="String(route.meta.title ?? '')">
    <div class="flex max-w-xl flex-col items-start gap-3">
      <v-icon class="text-surface-500" :icon="mdiProgressClock" size="32" />
      <h2 class="m-0 text-h3 text-surface-900">{{ route.meta.title }} isn’t built yet</h2>

      <p class="m-0 text-surface-600">
        It arrives in phase {{ route.meta.phase }} of the plan.
      </p>

      <v-btn class="text-primary" :to="{ name: 'dashboard' }" variant="outlined">Go to the dashboard</v-btn>
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import { mdiProgressClock } from '@mdi/js'
  import { useRoute } from 'vue-router'
  import PageBody from '@/components/PageBody.vue'

  // Stands in for pages of later phases, so the menus work on staging (IP: staff-only releases).
  const route = useRoute()
</script>
