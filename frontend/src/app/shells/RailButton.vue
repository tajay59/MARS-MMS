<template>
  <router-link v-slot="{ href, navigate }" custom :to="to">
    <a
      :aria-current="active ? 'true' : undefined"
      :aria-describedby="hintId"
      :aria-label="badge ? `${label}, ${badge}` : label"
      class="group relative flex size-11 shrink-0 items-center justify-center rounded-xl"
      :class="active
        ? 'bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100'
        : 'text-surface-600 hover:bg-surface-100 hover:text-surface-900'"
      :href="href"
      @click="navigate"
    >
      <v-icon :icon="icon" size="22" />
      <span v-if="badge" aria-hidden="true" class="absolute right-2 top-2 size-2 rounded-full bg-primary ring-2 ring-surface" />

      <!-- The rail never expands: this names the section and what it holds, on hover and on focus -->
      <RailTip :hint="badge ? `${hint} · ${badge}` : hint" :hint-id="hintId" :label="label" />
    </a>
  </router-link>
</template>

<script lang="ts" setup>
  import type { RouteLocationRaw } from 'vue-router'
  import { useId } from 'vue'
  import RailTip from './RailTip.vue'

  defineProps<{
    label: string
    hint: string
    icon: string
    to: RouteLocationRaw
    active?: boolean
    /** Something waits in the section, for example "2 waiting": a dot on the icon. */
    badge?: string | null
  }>()

  const hintId = useId()
</script>
