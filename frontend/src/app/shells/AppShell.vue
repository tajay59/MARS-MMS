<template>
  <a class="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[2000] focus:rounded-md focus:bg-surface focus:px-4 focus:py-2" href="#main">
    Skip to main content
  </a>

  <!--
    The app shell for staff and clients (DBD "The app shell"): three square tiles on the ground
    colour, 5 px apart: the rail, the interactive pane (choose a page, a record, filters) and the
    view (the details). On phones the pane and view fill the screen and the rail is a tab tile.
  -->
  <div
    class="flex h-dvh flex-col overflow-y-auto bg-surface pb-[calc(84px+env(safe-area-inset-bottom))] pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)] pt-[env(safe-area-inset-top)] md:flex-row md:gap-[5px] md:overflow-hidden md:bg-ground md:p-[5px]"
  >
    <AppRail v-if="mdAndUp" :badges="badges" :current="section" :sections="sections" />

    <section
      v-show="paneShown"
      aria-labelledby="pane-h"
      class="flex shrink-0 flex-col bg-surface md:min-h-0 md:w-[300px] lg:w-[360px] 2xl:w-[420px]"
    >
      <div class="flex min-h-14 shrink-0 items-center gap-1 pl-5 pr-3 pt-2">
        <h2 id="pane-h" class="m-0 grow truncate text-h2 text-surface-900">{{ paneTitle }}</h2>

        <v-btn
          v-if="lgAndUp"
          aria-label="Hide the list"
          icon
          size="36"
          variant="text"
          @click="toggle"
        >
          <v-icon class="text-surface-600" :icon="mdiDockLeft" size="20" />
        </v-btn>
      </div>

      <nav v-if="tabs.length > 1" :aria-label="`${paneTitle} pages`" class="flex flex-wrap gap-1 px-4 pt-2">
        <router-link
          v-for="tab in tabs"
          :key="tab.to"
          v-slot="{ href, navigate }"
          custom
          :to="{ name: tab.to }"
        >
          <a
            :aria-current="tab.to === route.name ? 'page' : undefined"
            class="inline-flex h-8 items-center gap-1.5 rounded-full px-3.5 text-sm font-medium"
            :class="tab.to === route.name
              ? 'bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100'
              : 'text-surface-600 hover:bg-surface-100 hover:text-surface-900'"
            :href="href"
            @click="navigate"
          >
            {{ tab.label }}
            <span v-if="tab.count" class="text-xs font-semibold tabular-nums">{{ tab.count }}<span class="sr-only"> waiting</span></span>
          </a>
        </router-link>
      </nav>

      <div
        ref="target"
        class="flex grow flex-col pb-4 md:min-h-0 md:overflow-y-auto"
        :class="tabs.length > 1 ? 'pt-3' : 'pt-1'"
      />
    </section>

    <main id="main" class="flex min-w-0 grow flex-col bg-surface outline-none md:min-h-0 md:overflow-hidden" tabindex="-1">
      <slot />
    </main>

    <AppTabBar v-if="!mdAndUp" :badges="badges" :current="section" :sections="sections" />
  </div>
</template>

<script lang="ts" setup>
  import { mdiDockLeft } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, provide, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { clientSections, sectionOf, sectionsFor, staffSections } from '@/app/navigation'
  import { useRegistrationsStore } from '@/stores/registrations'
  import { useSessionStore } from '@/stores/session'
  import AppRail from './AppRail.vue'
  import AppTabBar from './AppTabBar.vue'
  import { paneKey, shellKey } from './pane'

  const COLLAPSED_KEY = 'mms.pane.collapsed'

  const { mdAndUp, lgAndUp } = useDisplay()
  const session = useSessionStore()
  const { isAdmin, isClient, roles } = storeToRefs(session)
  const registrations = useRegistrationsStore()
  const route = useRoute()

  const sections = computed(() => sectionsFor(isClient.value ? clientSections : staffSections, roles.value))
  const section = computed(() => sectionOf(sections.value, route.name))
  const paneTitle = computed(() => section.value?.label ?? 'Account')
  const badges = computed<Record<string, string | null>>(() => {
    const waiting = registrations.label()
    return { admin: waiting ? `${waiting} waiting` : null }
  })
  const tabs = computed(() => (section.value?.items ?? []).map(item => ({
    ...item,
    count: item.to === 'admin-registrations' ? registrations.label() : null,
  })))

  // The pane, shared with pages through usePane() and <PaneContent>
  const target = ref<HTMLElement | null>(null)
  const blocks = ref(0)
  const selected = ref(false)
  const collapsed = ref(readCollapsed())
  const hasPane = computed(() => tabs.value.length > 1 || blocks.value > 0)
  const canExpand = computed(() => hasPane.value && collapsed.value && lgAndUp.value)
  // Phones show the list, then the record alone once one is open
  const paneShown = computed(() => hasPane.value && (mdAndUp.value ? !(lgAndUp.value && collapsed.value) : !selected.value))

  function toggle (): void {
    collapsed.value = !collapsed.value
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed.value ? '1' : '0')
    } catch {
      // A per-device convenience: without storage the pane opens again next time
    }
  }

  function readCollapsed (): boolean {
    try {
      return localStorage.getItem(COLLAPSED_KEY) === '1'
    } catch {
      return false
    }
  }

  provide(paneKey, { target, blocks, selected, collapsed, canExpand, toggle })
  provide(shellKey, 'app')

  watch(() => route.name, () => {
    if (isAdmin.value) {
      void registrations.refresh()
    }
  }, { immediate: true })
</script>
