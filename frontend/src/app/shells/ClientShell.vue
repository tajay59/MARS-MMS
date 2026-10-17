<template>
  <a class="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[2000] focus:rounded-md focus:bg-surface focus:px-4 focus:py-2" href="#main">
    Skip to main content
  </a>

  <v-app-bar border="b" class="bg-surface" flat height="64">
    <div class="flex w-full items-center gap-2 px-4 lg:gap-6 lg:px-6">
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

      <router-link :aria-label="`${APP_NAME} dashboard`" class="flex items-center" :to="{ name: 'dashboard' }">
        <AppLogo :size="32" :wordmark="mdAndUp" />
      </router-link>

      <nav v-if="mdAndUp" aria-label="Main" class="flex grow gap-1">
        <router-link
          v-for="item in clientMenu"
          :key="item.to"
          v-slot="{ href, navigate, isActive }"
          custom
          :to="{ name: item.to }"
        >
          <a
            :aria-current="isActive ? 'page' : undefined"
            class="flex h-10 items-center rounded-md px-3 text-sm font-medium hover:bg-surface-100"
            :class="isActive ? 'bg-primary-50 text-primary' : 'text-surface-700'"
            :href="href"
            @click="navigate"
          >{{ item.label }}</a>
        </router-link>
      </nav>

      <div class="ml-auto flex items-center gap-2">
        <!-- variant set here: VAppBar makes its buttons text by default -->
        <v-btn
          v-if="canAct"
          color="primary"
          :prepend-icon="mdAndUp ? mdiPlus : undefined"
          :to="{ name: 'request-new' }"
          variant="flat"
        >
          <v-icon v-if="!mdAndUp" :icon="mdiPlus" />
          <span :class="mdAndUp ? '' : 'sr-only'">Report a problem</span>
        </v-btn>

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
    </div>
  </v-app-bar>

  <v-navigation-drawer v-if="!mdAndUp" v-model="drawer" temporary>
    <div class="p-4"><AppLogo :size="32" /></div>

    <v-list aria-label="Main" nav tag="nav">
      <v-list-item
        v-for="item in clientMenu"
        :key="item.to"
        :prepend-icon="item.icon"
        :title="item.label"
        :to="{ name: item.to }"
      />
    </v-list>
  </v-navigation-drawer>

  <v-main id="main" class="bg-background" tabindex="-1">
    <div class="mx-auto w-full max-w-[1120px] px-4 py-8 md:px-6 md:py-12">
      <slot />
    </div>
  </v-main>
</template>

<script lang="ts" setup>
  import { mdiMenu, mdiPlus } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { ref } from 'vue'
  import { useDisplay } from 'vuetify'
  import { APP_NAME } from '@/app/brand'
  import { clientMenu } from '@/app/navigation'
  import { icons } from '@/app/theme/icons'
  import AppLogo from '@/components/AppLogo.vue'
  import UserMenu from '@/components/UserMenu.vue'
  import { useSessionStore } from '@/stores/session'

  // Client shell: white 64 px top bar, centred content up to 1120 px (DBD "The three shells").
  const { mdAndUp } = useDisplay()
  const { canAct } = storeToRefs(useSessionStore())
  const drawer = ref(false)
</script>
