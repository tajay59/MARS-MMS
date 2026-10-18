<template>
  <!--
    Phones and tablets below 1024 px: the rail becomes a bar docked to the bottom edge, translucent
    over the content, with the home indicator's inset below it (F13). The section open is a filled
    pill; the others are bare icons with a hover tint. Labels stay visible (DBD: nothing by hover only).
  -->
  <nav
    aria-label="Main"
    class="fixed inset-x-0 bottom-0 z-[1004] border-t border-surface-200 bg-surface/85 pb-[max(8px,env(safe-area-inset-bottom))] pl-[max(12px,env(safe-area-inset-left))] pr-[max(12px,env(safe-area-inset-right))] pt-2 shadow-[0_-8px_32px_rgb(0_0_0/0.08)] backdrop-blur-xl dark:shadow-[0_-8px_32px_rgb(0_0_0/0.45)]"
  >
    <div class="mx-auto grid max-w-md grid-cols-5 items-center justify-items-center">
      <router-link
        v-for="section in shown"
        :key="section.key"
        v-slot="{ href, navigate }"
        custom
        :to="{ name: section.items[0]!.to }"
      >
        <a
          :aria-current="section.key === current?.key ? 'true' : undefined"
          class="group flex w-full min-w-0 flex-col items-center justify-center py-1"
          :href="href"
          @click="navigate"
        >
          <span :class="pill(section.key === current?.key)">
            <v-icon :icon="section.icon" :size="section.key === current?.key ? 20 : 22" />
          </span>

          <span :class="label(section.key === current?.key)">{{ section.label }}</span>
        </a>
      </router-link>

      <v-menu location="top end" :offset="8">
        <template #activator="{ props: activator }">
          <button
            v-bind="activator"
            class="group flex w-full min-w-0 flex-col items-center justify-center py-1"
            type="button"
          >
            <span :class="pill(inMe)">
              <v-icon :icon="mdiAccountCircleOutline" :size="inMe ? 20 : 22" />
              <!-- On the filled pill the dot sits on its corner, where it can still be seen -->
              <span
                v-if="meBadge"
                aria-hidden="true"
                class="absolute size-2.5 rounded-full bg-primary ring-2 ring-surface"
                :class="inMe ? '-right-0.5 -top-0.5' : 'right-1 top-1'"
              />
            </span>

            <span :class="label(inMe)">Me<span v-if="meBadge" class="sr-only">, {{ meBadge }}</span></span>
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
    </div>
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

  // Written out in full so Tailwind finds each class
  function pill (active: boolean): string {
    return active
      ? 'relative flex items-center justify-center rounded-full bg-primary px-4 py-1.5 text-on-primary shadow-md shadow-primary/35 transition-transform duration-200 group-active:scale-95'
      : 'relative flex items-center justify-center rounded-xl p-1.5 text-surface-600 transition duration-200 group-hover:bg-surface-100 group-hover:text-surface-900 group-active:scale-95'
  }

  function label (active: boolean): string {
    return active
      ? 'mt-1 max-w-full truncate text-xs font-bold tracking-tight text-primary-700 dark:text-primary-200'
      : 'mt-0.5 max-w-full truncate text-xs font-medium tracking-tight text-surface-600 group-hover:text-surface-900'
  }

  async function logOut (): Promise<void> {
    await session.logout()
    await router.replace({ name: 'login' })
  }
</script>
