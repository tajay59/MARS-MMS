<template>
  <router-link v-slot="{ href, navigate, isActive }" custom :to="{ name: item.to }">
    <a
      :aria-current="isActive ? 'page' : undefined"
      :aria-label="rail ? item.label : undefined"
      class="flex h-10 items-center gap-3 rounded-md px-3 text-sm hover:bg-white/10"
      :class="isActive ? 'bg-white/15 font-semibold text-white' : 'font-medium text-primary-100'"
      :href="href"
      :title="rail ? item.label : undefined"
      @click="navigate"
    >
      <v-icon :class="isActive ? 'text-white' : 'text-primary-300'" :icon="item.icon" size="20" />

      <template v-if="!rail">
        <span class="grow truncate">{{ item.label }}</span>

        <span
          v-if="count"
          class="min-w-5 rounded-full bg-warning-container px-1.5 text-center text-xs font-semibold leading-5 text-on-warning-container"
        ><span class="sr-only">, </span>{{ count }}<span class="sr-only"> waiting</span></span>
      </template>
    </a>
  </router-link>
</template>

<script lang="ts" setup>
  import type { MenuItem } from '@/app/navigation'

  defineProps<{ item: MenuItem, rail?: boolean, count?: string | null }>()
</script>
