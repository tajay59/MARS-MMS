<template>
  <PageBody
    :back="part ? { name: 'admin-settings' } : undefined"
    back-label="Back to settings"
    :subtitle="current?.subtitle"
    :title="current?.label ?? 'Settings'"
  >
    <!-- The pane: the parts of Settings; the one chosen opens in the view -->
    <PaneContent>
      <ul aria-label="Settings" class="m-0 flex list-none flex-col gap-0.5 p-0 px-2">
        <li
          v-for="item in PARTS"
          :key="item.id"
          class="relative flex items-center gap-3 rounded-card p-3"
          :class="shown === item.id ? 'bg-primary-50' : 'hover:bg-surface-100'"
        >
          <span
            aria-hidden="true"
            class="flex size-10 shrink-0 items-center justify-center rounded-xl"
            :class="shown === item.id ? 'bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100' : 'bg-surface-100 text-surface-600'"
          >
            <v-icon :icon="item.icon" size="20" />
          </span>

          <div class="flex min-w-0 flex-col gap-0.5">
            <router-link
              :aria-current="shown === item.id ? 'page' : undefined"
              class="font-medium text-surface-900 after:absolute after:inset-0 after:rounded-card"
              :to="{ name: 'admin-settings', params: { part: item.id } }"
            >{{ item.label }}</router-link>

            <span class="text-sm text-surface-600">{{ item.subtitle }}</span>
          </div>
        </li>
      </ul>
    </PaneContent>

    <AppearanceSettings v-if="shown === 'appearance'" />
    <BrandColours v-else-if="shown === 'colours'" />
    <p v-else class="m-0 text-surface-600">Choose what to change.</p>
  </PageBody>
</template>

<script lang="ts" setup>
  import { computed } from 'vue'
  import { useRoute } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { usePaneSelection } from '@/app/shells/pane'
  import { icons } from '@/app/theme/icons'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import AppearanceSettings from './AppearanceSettings.vue'
  import BrandColours from './BrandColours.vue'

  // /admin/settings/:part (decision W4-11). The part is in the URL, like a record, so a reload or
  // Back keeps the place; from 768 px the first part opens when none is chosen.
  type Part = 'appearance' | 'colours'

  const PARTS = [
    { id: 'appearance', label: 'Appearance', subtitle: 'Your theme and animations', icon: icons.themeSystem },
    { id: 'colours', label: 'Brand colours', subtitle: 'The colours everyone sees', icon: icons.palette },
  ] as const satisfies readonly { id: Part, label: string, subtitle: string, icon: string }[]

  const route = useRoute()
  const { mdAndUp } = useDisplay()
  const part = computed<Part | null>(() => {
    const value = route.params.part
    return value === 'appearance' || value === 'colours' ? value : null
  })
  const shown = computed<Part | null>(() => part.value ?? (mdAndUp.value ? 'appearance' : null))
  const current = computed(() => PARTS.find(p => p.id === shown.value))
  usePaneSelection(() => part.value !== null)
</script>
