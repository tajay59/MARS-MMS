<template>
  <div class="mx-auto max-w-[1120px] px-4 py-12 md:px-6">
    <h1 class="text-display text-surface-900">AWS-MMS</h1>

    <p class="mt-2 max-w-prose text-body text-surface-600">
      The frontend foundation is in place: brand themes, fonts, icons and layers.
      The shells and pages are built in Phase 1 of the implementation plan.
    </p>

    <v-card class="mt-8 p-6">
      <h2 class="text-h3 text-surface-900">Appearance</h2>

      <v-btn-toggle
        class="mt-4"
        density="comfortable"
        divided
        mandatory
        :model-value="themeStore.preference"
        variant="outlined"
        @update:model-value="themeStore.setPreference"
      >
        <v-btn :prepend-icon="icons.themeLight" value="light">Light</v-btn>
        <v-btn :prepend-icon="icons.themeDark" value="dark">Dark</v-btn>
        <v-btn :prepend-icon="icons.themeSystem" value="system">System</v-btn>
      </v-btn-toggle>
    </v-card>
  </div>
</template>

<script lang="ts" setup>
  import { icons } from '@/app/theme/icons'
  import { useThemeStore } from '@/stores/theme'

  const themeStore = useThemeStore()
</script>
