<template>
  <!-- The rail: a slim tile of section icons that never expands (DBD "The app shell") -->
  <nav aria-label="Main" class="relative z-[3] flex w-16 shrink-0 flex-col items-center gap-1 bg-surface py-3">
    <router-link
      :aria-label="`${APP_NAME} dashboard`"
      class="mb-3 flex size-11 shrink-0 items-center justify-center rounded-xl"
      :to="{ name: 'dashboard' }"
    >
      <AppLogo :size="32" :wordmark="false" />
    </router-link>

    <RailButton
      v-for="section in sections"
      :key="section.key"
      :active="section.key === current?.key"
      :badge="badges[section.key]"
      :hint="section.hint"
      :icon="section.icon"
      :label="section.label"
      :to="{ name: section.items[0]!.to }"
    />

    <div class="grow" />

    <RailButton
      v-if="!isClient"
      :active="route.name === 'sync'"
      hint="Nothing is waiting on this device"
      :icon="mdiCloudCheckOutline"
      label="Sync"
      :to="{ name: 'sync' }"
    />

    <RailButton
      :active="route.name === 'notifications'"
      hint="Updates on requests, visits and reports"
      :icon="icons.notifications"
      label="Notifications"
      :to="{ name: 'notifications' }"
    />

    <div class="mt-1 flex size-11 shrink-0 items-center justify-center">
      <UserMenu rail />
    </div>
  </nav>
</template>

<script lang="ts" setup>
  import type { Section } from '@/app/navigation'
  import { mdiCloudCheckOutline } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { useRoute } from 'vue-router'
  import { APP_NAME } from '@/app/brand'
  import { icons } from '@/app/theme/icons'
  import AppLogo from '@/components/AppLogo.vue'
  import UserMenu from '@/components/UserMenu.vue'
  import { useSessionStore } from '@/stores/session'
  import RailButton from './RailButton.vue'

  defineProps<{
    sections: Section[]
    current?: Section
    /** Per section key, what waits there ("2 waiting"); shown as a dot. */
    badges: Record<string, string | null>
  }>()

  const route = useRoute()
  const { isClient } = storeToRefs(useSessionStore())
</script>
