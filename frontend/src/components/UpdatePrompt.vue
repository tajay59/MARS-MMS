<template>
  <v-snackbar
    v-model="updates.visible"
    class="mt-16"
    color="surface"
    content-class="border border-surface-200 border-l-4 border-l-info rounded-card"
    location="top end"
    :timeout="-1"
    width="380"
  >
    <div class="flex items-start gap-3">
      <v-icon class="mt-0.5 shrink-0 text-info" :icon="mdiRefresh" size="20" />

      <div>
        <p class="m-0 font-semibold text-surface-900">A new version of {{ APP_NAME }} is ready</p>

        <p class="m-0 text-sm text-surface-600">
          Reload when you’re ready. Anything you haven’t saved on this page stays until you reload.
        </p>
      </div>
    </div>

    <template #actions>
      <v-btn class="text-primary" variant="text" @click="updates.later()">Later</v-btn>
      <v-btn class="text-primary" variant="outlined" @click="updates.reload()">Reload now</v-btn>
    </template>
  </v-snackbar>
</template>

<script lang="ts" setup>
  import { mdiRefresh } from '@mdi/js'
  import { APP_NAME } from '@/app/brand'
  import { useUpdateStore } from '@/stores/update'

  // The update prompt (pwa skill service-worker.md §3): never a silent reload.
  const updates = useUpdateStore()
</script>
