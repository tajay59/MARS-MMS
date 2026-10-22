<template>
  <v-defaults-provider :defaults="fieldDefaults">
    <v-app-bar border="b" class="bg-surface" flat height="56">
      <div class="flex w-full items-center gap-2 pr-[max(4px,env(safe-area-inset-right))]" :class="fieldBar.back ? 'pl-[max(4px,env(safe-area-inset-left))]' : 'pl-[max(16px,env(safe-area-inset-left))]'">
        <v-btn
          v-if="fieldBar.back"
          :active="false"
          :aria-label="fieldBar.backLabel"
          icon
          :size="48"
          :to="fieldBar.back"
          variant="text"
        >
          <v-icon class="text-surface-700" :icon="mdiArrowLeft" />
        </v-btn>

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
      :height="64"
      tag="nav"
    >
      <!-- The page open: coloured icon and label with a dot below, no background (same as AppTabBar) -->
      <router-link
        v-for="item in fieldMenu"
        :key="item.to"
        v-slot="{ href, navigate }"
        custom
        :to="{ name: item.to }"
      >
        <a
          :aria-current="route.name === item.to ? 'page' : undefined"
          :class="[tabItem, 'flex-1']"
          :href="href"
          @click="onLink($event, navigate)"
          @pointercancel="tabUp"
          @pointerdown="tabDown"
          @pointerleave="tabUp"
          @pointerup="tabUp"
        >
          <span :class="tabIcon(route.name === item.to)" data-tab-icon>
            <v-icon :icon="item.icon" :size="22" />
          </span>

          <span :class="tabLabel(route.name === item.to)">{{ item.label }}</span>

          <span aria-hidden="true" :class="tabDot(route.name === item.to)" />
        </a>
      </router-link>
    </v-bottom-navigation>
  </v-defaults-provider>
</template>

<script lang="ts" setup>
  import { mdiArrowLeft } from '@mdi/js'
  import { computed, provide } from 'vue'
  import { useRoute } from 'vue-router'
  import { fieldMenu } from '@/app/navigation'
  import SyncBadge from '@/components/SyncBadge.vue'
  import { fieldBar } from './fieldBar'
  import { shellKey } from './pane'
  import { tabDot, tabDown, tabIcon, tabItem, tabKey, tabLabel, tabUp } from './tabBar'

  // Field shell for staff on phones: 56 px app bar, 64 px bottom bar, 48 px targets (DBD, TRD §13.2).
  const route = useRoute()
  provide(shellKey, 'field')

  function onLink (event: MouseEvent, navigate: (event: MouseEvent) => void): void {
    tabKey(event)
    navigate(event)
  }

  const title = computed(() => fieldBar.title ?? route.meta.title ?? '')

  const fieldDefaults = {
    VBtn: { height: 48 },
    VTextField: { density: 'comfortable' },
  }
</script>
