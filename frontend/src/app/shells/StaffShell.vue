<template>
  <a class="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[2000] focus:rounded-md focus:bg-surface focus:px-4 focus:py-2" href="#main">
    Skip to main content
  </a>
  <!-- Sidebar: 248 px, primary-900; an icon rail on tablets, a drawer on phones (DBD) -->
  <v-navigation-drawer
    v-model="drawer"
    class="bg-primary-900 text-primary-100 dark:border-r dark:border-surface-200"
    :permanent="mdAndUp"
    :rail="md"
    :temporary="!mdAndUp"
    width="248"
  >
    <nav aria-label="Main" class="flex flex-col gap-1 px-3 py-4">
      <router-link
        :aria-label="`${APP_NAME} dashboard`"
        class="mb-4 flex h-10 items-center px-1"
        :to="{ name: 'dashboard' }"
      >
        <AppLogo :size="md ? 32 : 30" surface="dark" :wordmark="!md" />
      </router-link>

      <SidebarLink v-for="item in mainItems" :key="item.to" :item="item" :rail="md" />

      <template v-if="isAdmin">
        <div class="my-3 h-px bg-white/10" role="separator" />
        <p v-if="!md" id="admin-menu" class="m-0 px-3 py-1 text-xs font-medium text-primary-300">Admin</p>

        <SidebarLink
          v-for="item in adminMenu"
          :key="item.to"
          :count="item.to === 'admin-registrations' ? registrations.label() : null"
          :item="item"
          :rail="md"
        />
      </template>
    </nav>
  </v-navigation-drawer>

  <v-app-bar border="b" class="bg-surface" flat height="56">
    <div class="flex w-full items-center gap-2 pl-2 pr-4 md:gap-4 md:pl-6">
      <v-btn
        v-if="!mdAndUp"
        aria-label="Open menu"
        icon
        size="40"
        variant="text"
        @click="drawer = true"
      >
        <v-icon :icon="mdiMenu" />
      </v-btn>

      <h1 class="m-0 grow truncate text-h2 text-surface-900">{{ title }}</h1>
      <SyncBadge />

      <v-btn
        aria-label="Notifications"
        icon
        size="40"
        :to="{ name: 'notifications' }"
        variant="text"
      >
        <v-icon class="text-surface-600" :icon="icons.notifications" size="20" />
      </v-btn>

      <UserMenu />
    </div>
  </v-app-bar>

  <v-main id="main" class="bg-background" tabindex="-1">
    <slot />
  </v-main>
</template>

<script lang="ts" setup>
  import { mdiMenu } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { APP_NAME } from '@/app/brand'
  import { adminMenu, staffMenu, visibleTo } from '@/app/navigation'
  import { icons } from '@/app/theme/icons'
  import AppLogo from '@/components/AppLogo.vue'
  import SyncBadge from '@/components/SyncBadge.vue'
  import UserMenu from '@/components/UserMenu.vue'
  import { useRegistrationsStore } from '@/stores/registrations'
  import { useSessionStore } from '@/stores/session'
  import SidebarLink from './SidebarLink.vue'

  // Staff shell: sidebar, 56 px top bar with the page title (DBD "The three shells").
  const { mdAndUp, md } = useDisplay()
  const session = useSessionStore()
  const { isAdmin, roles } = storeToRefs(session)
  const registrations = useRegistrationsStore()
  const route = useRoute()

  const drawer = ref(mdAndUp.value)
  watch(mdAndUp, wide => {
    drawer.value = wide
  })
  const mainItems = computed(() => visibleTo(staffMenu, roles.value))
  const title = computed(() => route.meta.title ?? '')

  watch(() => route.name, () => {
    if (isAdmin.value) {
      void registrations.refresh()
    }
  }, { immediate: true })
</script>
