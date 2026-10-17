<template>
  <v-menu :location="rail ? 'end bottom' : 'bottom end'" :offset="rail ? 10 : 4">
    <template #activator="{ props: activator }">
      <span class="group relative flex">
        <!-- The initials are decoration; the name comes from the hidden text (WCAG 2.5.3) -->
        <button
          v-bind="menuButton(activator)"
          class="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-100 text-sm font-semibold text-primary-600 dark:bg-primary-50 dark:text-primary"
          type="button"
        >
          <span aria-hidden="true">{{ initials }}</span>
          <span class="sr-only">Account menu for {{ user?.name }}</span>
        </button>

        <RailTip v-if="rail" :hint="'Profile and log out'" :hint-id="hintId" :label="user?.name ?? ''" />
      </span>
    </template>

    <v-card class="min-w-60 border border-surface-200 py-1">
      <div class="px-4 py-2">
        <p class="m-0 text-sm font-semibold text-surface-900">{{ user?.name }}</p>
        <p class="m-0 text-sm text-surface-600">{{ user?.email }}</p>
      </div>

      <v-divider class="my-1" />

      <v-list aria-label="Account" class="py-0" density="compact" role="menu">
        <v-list-item :prepend-icon="mdiAccountOutline" role="menuitem" title="My profile" :to="{ name: 'profile' }" />

        <v-list-item
          v-for="item in extra"
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
</template>

<script lang="ts" setup>
  import type { MenuItem } from '@/app/navigation'
  import { mdiAccountOutline, mdiLogout } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, useId } from 'vue'
  import { useRouter } from 'vue-router'
  import RailTip from '@/app/shells/RailTip.vue'
  import { useSessionStore } from '@/stores/session'

  // Avatar with initials: Profile and Log out (AFD §5.1). On the rail it opens to the side.
  defineProps<{
    rail?: boolean
    /** More pages to list between My profile and Log out. */
    extra?: MenuItem[]
  }>()

  const session = useSessionStore()
  const { user } = storeToRefs(session)
  const router = useRouter()
  const hintId = useId()

  const initials = computed(() => (user.value?.name ?? '')
    .split(/\s+/)
    .filter(Boolean)
    .map(part => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase())

  /*
    Vuetify’s activator also sets aria-owns, which puts the whole menu inside the button for
    screen readers (its name becomes "… My profile Log out"). aria-controls is enough.
  */
  function menuButton (props: Record<string, unknown>): Record<string, unknown> {
    const { 'aria-owns': _owns, ...rest } = props
    return rest
  }

  async function logOut (): Promise<void> {
    await session.logout()
    await router.replace({ name: 'login' })
  }
</script>
