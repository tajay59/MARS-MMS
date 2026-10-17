<template>
  <v-defaults-provider :defaults="fieldDefaults">
    <v-app-bar border="b" class="bg-surface" flat height="56">
      <div class="flex w-full items-center gap-2 pl-[max(16px,env(safe-area-inset-left))] pr-[max(4px,env(safe-area-inset-right))]">
        <h1 class="m-0 grow truncate text-lg font-semibold text-surface-900">{{ title }}</h1>
        <SyncBadge />
      </div>
    </v-app-bar>

    <!-- overscroll-none: no rubber-banding of the whole app in standalone mode (manifest-install.md §5) -->
    <v-main id="main" class="overscroll-none bg-background">
      <div class="flex min-h-full flex-col pb-[env(safe-area-inset-bottom)] pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)]">
        <slot />
      </div>
    </v-main>

    <!-- 64 px plus the home indicator's safe area (F13) -->
    <v-bottom-navigation
      aria-label="Field"
      border="t"
      class="bg-surface pb-[env(safe-area-inset-bottom)]"
      grow
      :height="64"
      tag="nav"
    >
      <v-btn
        v-for="item in fieldMenu"
        :key="item.to"
        :aria-current="route.name === item.to ? 'page' : undefined"
        :class="route.name === item.to ? 'font-semibold text-primary' : 'text-surface-600'"
        height="64"
        :to="{ name: item.to }"
      >
        <v-icon :icon="item.icon" size="24" />
        <span class="text-xs">{{ item.label }}</span>
      </v-btn>
    </v-bottom-navigation>
  </v-defaults-provider>
</template>

<script lang="ts" setup>
  import { computed } from 'vue'
  import { useRoute } from 'vue-router'
  import { fieldMenu } from '@/app/navigation'
  import SyncBadge from '@/components/SyncBadge.vue'

  // Field shell for staff on phones: 56 px app bar, 64 px bottom bar, 48 px targets (DBD, TRD §13.2).
  const route = useRoute()
  const title = computed(() => route.meta.title ?? '')

  const fieldDefaults = {
    VBtn: { height: 48 },
    VTextField: { density: 'comfortable' },
  }
</script>
