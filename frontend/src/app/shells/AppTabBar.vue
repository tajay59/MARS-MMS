<template>
  <!-- Phones: the rail becomes a floating tab tile, 5 px from the edges, above the home indicator (F13) -->
  <nav
    aria-label="Main"
    class="fixed bottom-[calc(5px+env(safe-area-inset-bottom))] left-[max(5px,env(safe-area-inset-left))] right-[max(5px,env(safe-area-inset-right))] z-[1004] grid h-16 grid-cols-5 bg-ground px-1 shadow-lg"
  >
    <router-link
      v-for="section in shown"
      :key="section.key"
      v-slot="{ href, navigate }"
      custom
      :to="{ name: section.items[0]!.to }"
    >
      <a
        :aria-current="section.key === current?.key ? 'true' : undefined"
        class="flex min-w-0 flex-col items-center justify-center gap-0.5 text-xs font-medium"
        :class="section.key === current?.key ? 'text-primary-700 dark:text-primary-100' : 'text-surface-600'"
        :href="href"
        @click="navigate"
      >
        <span
          class="flex h-7 w-13 items-center justify-center rounded-full"
          :class="section.key === current?.key ? 'bg-primary-100 dark:bg-primary-800' : ''"
        >
          <v-icon :icon="section.icon" size="22" />
        </span>

        <span class="max-w-full truncate">{{ section.label }}</span>
      </a>
    </router-link>

    <v-menu location="top end" :offset="8">
      <template #activator="{ props: activator }">
        <button
          v-bind="activator"
          class="flex min-w-0 flex-col items-center justify-center gap-0.5 text-xs font-medium"
          :class="inMe ? 'text-primary-700 dark:text-primary-100' : 'text-surface-600'"
          type="button"
        >
          <span class="relative flex h-7 w-13 items-center justify-center rounded-full" :class="inMe ? 'bg-primary-100 dark:bg-primary-800' : ''">
            <v-icon :icon="mdiAccountCircleOutline" size="22" />
            <span v-if="meBadge" aria-hidden="true" class="absolute right-3 top-0.5 size-2 rounded-full bg-primary ring-2 ring-ground" />
          </span>

          <span>Me<span v-if="meBadge" class="sr-only">, {{ meBadge }}</span></span>
        </button>
      </template>

      <v-card class="min-w-64 border border-surface-200 py-1">
        <div class="px-4 py-2">
          <p class="m-0 text-sm font-semibold text-surface-900">{{ user?.name }}</p>
          <p class="m-0 text-sm text-surface-600">{{ user?.email }}</p>
        </div>

        <v-divider class="my-1" />

        <v-list aria-label="Me" class="py-0" role="menu">
          <v-list-item
            v-for="item in meItems"
            :key="item.to"
            :prepend-icon="item.icon"
            role="menuitem"
            :title="item.label"
            :to="{ name: item.to }"
          />

          <v-list-item :prepend-icon="mdiLogout" role="menuitem" title="Log out" @click="logOut" />
        </v-list>
      </v-card>
    </v-menu>
  </nav>
</template>

<script lang="ts" setup>
  import type { MenuItem, Section } from '@/app/navigation'
  import { mdiAccountCircleOutline, mdiAccountOutline, mdiCloudCheckOutline, mdiLogout } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed } from 'vue'
  import { useRouter } from 'vue-router'
  import { icons } from '@/app/theme/icons'
  import { useSessionStore } from '@/stores/session'

  const props = defineProps<{
    sections: Section[]
    current?: Section
    badges: Record<string, string | null>
  }>()

  const session = useSessionStore()
  const { user, isClient } = storeToRefs(session)
  const router = useRouter()

  // Four sections fit beside Me; Admin moves into the Me menu on phones.
  const shown = computed(() => props.sections.filter(s => s.key !== 'admin').slice(0, 4))
  const admin = computed(() => props.sections.find(s => s.key === 'admin'))
  const meBadge = computed(() => admin.value ? props.badges[admin.value.key] : null)

  const meItems = computed<MenuItem[]>(() => [
    { label: 'My profile', to: 'profile', icon: mdiAccountOutline },
    { label: 'Notifications', to: 'notifications', icon: icons.notifications },
    ...(isClient.value ? [] : [{ label: 'Sync', to: 'sync', icon: mdiCloudCheckOutline }]),
    ...(admin.value ? [{ label: meBadge.value ? `Admin (${meBadge.value})` : 'Admin', to: admin.value.items[0]!.to, icon: admin.value.icon }] : []),
  ])
  const inMe = computed(() => !shown.value.some(s => s.key === props.current?.key))

  async function logOut (): Promise<void> {
    await session.logout()
    await router.replace({ name: 'login' })
  }
</script>
