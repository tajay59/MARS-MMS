<template>
  <!-- A small app shell in one theme's colours: ground, rail, pane and view (DBD "The app shell") -->
  <figure class="m-0 flex min-w-0 flex-col gap-2">
    <div
      :aria-label="`${dark ? 'Dark' : 'Light'} theme: the app shell in these colours`"
      class="flex h-44 gap-[3px] overflow-hidden rounded-card border p-[3px]"
      role="img"
      :style="{ background: c.ground, borderColor: c['surface-200'] }"
    >
      <div class="flex w-8 shrink-0 flex-col items-center gap-2 rounded-[4px] py-2" :style="{ background: c.surface }">
        <span class="size-4 rounded-full" :style="{ background: c.primary }" />
        <span class="mt-1 size-5 rounded-md" :style="{ background: activeFill }" />
        <span v-for="n in 3" :key="n" class="h-1.5 w-3 rounded-full" :style="{ background: c['surface-500'] }" />
      </div>

      <div class="flex w-[38%] shrink-0 flex-col gap-1.5 rounded-[4px] p-2" :style="{ background: c.surface }">
        <span class="h-2 w-1/2 rounded-full" :style="{ background: c['on-surface'] }" />

        <div class="flex gap-1">
          <span class="h-3 w-8 rounded-full" :style="{ background: activeFill }" />
          <span class="h-3 w-6 rounded-full" :style="{ background: c['surface-100'] }" />
        </div>

        <div
          v-for="(row, i) in ROWS"
          :key="i"
          class="flex items-center gap-1.5 rounded-md p-1"
          :style="{ background: i === 0 ? c['primary-50'] : 'transparent' }"
        >
          <span class="size-4 shrink-0 rounded-full" :style="{ backgroundImage: `linear-gradient(135deg, ${c[row[0]]}, ${c[row[1]]})` }" />

          <span class="flex min-w-0 grow flex-col gap-1">
            <span class="h-1.5 w-4/5 rounded-full" :style="{ background: c['on-surface'] }" />
            <span class="h-1 w-1/2 rounded-full" :style="{ background: c['surface-600'] }" />
          </span>
        </div>
      </div>

      <div class="flex min-w-0 grow flex-col gap-2 rounded-[4px] p-2.5" :style="{ background: c.surface }">
        <span class="h-2.5 w-2/3 rounded-full" :style="{ background: c['on-surface'] }" />
        <span class="h-1.5 w-1/3 rounded-full" :style="{ background: c['surface-600'] }" />
        <span class="h-px w-full" :style="{ background: c['surface-200'] }" />

        <span class="flex items-center gap-1.5 rounded-md border-l-2 px-2 py-1.5" :style="{ background: c['info-container'], borderColor: c.info }">
          <span class="h-1.5 w-3/4 rounded-full" :style="{ background: c['on-info-container'] }" />
        </span>

        <span class="h-1.5 w-11/12 rounded-full" :style="{ background: c['surface-300'] }" />
        <span class="h-1.5 w-4/5 rounded-full" :style="{ background: c['surface-300'] }" />

        <span class="mt-auto flex justify-end gap-1.5">
          <span class="rounded-[4px] border px-2 py-0.5 text-[10px] font-semibold leading-4" :style="{ borderColor: c.primary, color: c.primary }">Reject</span>
          <span class="rounded-[4px] px-2 py-0.5 text-[10px] font-semibold leading-4" :style="{ background: c.primary, color: c['on-primary'] }">Approve</span>
        </span>
      </div>
    </div>

    <figcaption class="text-sm text-surface-600">{{ dark ? 'Dark' : 'Light' }}</figcaption>
  </figure>
</template>

<script lang="ts" setup>
  import type { MaterialTheme } from '@/app/theme/material'
  import { computed } from 'vue'
  import { materialColors } from '@/app/theme/material'

  const props = defineProps<{ theme: MaterialTheme, dark?: boolean }>()

  // The avatar gradients of the first rows (components/UserAvatar.vue)
  const ROWS = [
    ['primary-600', 'tertiary-600'],
    ['secondary-600', 'primary-700'],
    ['tertiary-600', 'secondary-700'],
  ] as const

  const c = computed(() => materialColors(props.theme, props.dark ?? false))
  const activeFill = computed(() => c.value[props.dark ? 'primary-800' : 'primary-100'])
</script>
