<template>
  <li class="relative">
    <a
      class="flex min-h-16 items-center gap-3.5 rounded-2xl px-4 py-3 no-underline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary"
      :class="item.read ? 'text-surface-900 hover:bg-surface-50' : 'bg-primary-50 text-surface-900'"
      :href="item.link"
      @click.prevent="emit('open', item)"
    >
      <span
        aria-hidden="true"
        class="grid size-10 shrink-0 place-items-center rounded-full"
        :class="item.read ? 'bg-surface-100 text-surface-600' : 'bg-primary-100 text-primary-800 dark:bg-primary-800 dark:text-primary-100'"
      >
        <v-icon :icon="iconFor(item.type)" size="20" />
      </span>

      <span class="flex min-w-0 grow flex-col">
        <span class="truncate" :class="item.read ? 'font-medium' : 'font-semibold'">{{ item.title }}</span>
        <span class="truncate text-sm text-surface-600">{{ item.body }}</span>
      </span>

      <span class="flex shrink-0 flex-col items-end gap-1.5">
        <time class="text-sm tabular-nums text-surface-600" :datetime="item.created_at">{{ formatListTime(item.created_at) }}</time>
        <span v-if="!item.read" aria-hidden="true" class="size-2.5 rounded-full bg-primary" />
      </span>

      <span v-if="!item.read" class="sr-only">Unread</span>
    </a>
  </li>
</template>

<script lang="ts" setup>
  import type { NotificationOut } from '@/api/models'
  import { formatListTime } from '@/app/format'
  import { iconFor } from './notifications'

  // One notification: what happened, to which request, and when. A link, so it opens in a new
  // tab with a modified click like any other; a plain click marks it read first.
  defineProps<{ item: NotificationOut }>()
  const emit = defineEmits<{ open: [item: NotificationOut] }>()
</script>
