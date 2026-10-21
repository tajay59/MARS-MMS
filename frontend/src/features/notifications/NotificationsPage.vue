<template>
  <PageBody :subtitle="subtitle" title="Notifications" wide>
    <template #actions>
      <span class="live-chip inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium" :class="liveClass">
        <span aria-hidden="true" class="size-2 rounded-full bg-current" />{{ liveText }}
      </span>

      <v-btn
        v-if="store.unread > 0"
        color="primary"
        :prepend-icon="mdiCheckAll"
        variant="tonal"
        @click="store.markAllRead()"
      >Mark all as read</v-btn>
    </template>

    <!-- The pane: all or unread, then the kind -->
    <PaneContent pin>
      <div class="flex flex-col gap-4 px-3">
        <div aria-label="Show" class="flex flex-col gap-0.5" role="group">
          <button
            v-for="option in views"
            :key="option.key"
            :aria-pressed="view === option.key"
            class="flex h-11 items-center justify-between rounded-card px-3 text-left text-sm font-medium"
            :class="view === option.key ? 'bg-primary-100 text-primary-800 dark:bg-primary-800 dark:text-primary-100' : 'text-surface-900 hover:bg-surface-100'"
            type="button"
            @click="setView(option.key)"
          >
            <span>{{ option.label }}</span>
            <span class="tabular-nums" :class="option.key === 'unread' ? 'font-semibold' : 'text-surface-600'">{{ option.count }}</span>
          </button>
        </div>

        <div v-if="kinds.length > 0" aria-labelledby="nf-kind" class="flex flex-col gap-0.5" role="group">
          <h3 id="nf-kind" class="m-0 px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-surface-600">Type</h3>

          <button
            v-for="kind in kinds"
            :key="kind.key"
            :aria-pressed="kindKey === kind.key"
            class="flex h-10 items-center justify-between rounded-card px-3 text-left text-sm"
            :class="kindKey === kind.key ? 'bg-primary-50 font-medium text-surface-900' : 'text-surface-900 hover:bg-surface-100'"
            type="button"
            @click="kindKey = kindKey === kind.key ? null : kind.key"
          >
            <span>{{ kind.label }}</span>
            <span class="tabular-nums text-surface-600">{{ kind.count }}</span>
          </button>
        </div>

        <router-link class="mx-1 mt-2 inline-flex h-10 items-center gap-2 self-start rounded-card px-3 text-sm font-medium text-primary no-underline hover:bg-surface-100" :to="{ name: 'profile' }">
          <v-icon :icon="mdiEmailOutline" size="18" />Email preferences
        </router-link>
      </div>
    </PaneContent>

    <FeedbackBanner v-if="store.error && !store.loaded" :type="store.error === 'offline' ? 'warning' : 'error'">
      {{ store.error === 'offline' ? 'This needs a connection. Your notifications will load when you have signal.' : 'We couldn’t load your notifications. Reload the page to try again.' }}
    </FeedbackBanner>

    <div v-else-if="!store.loaded" aria-label="Loading notifications…" role="status">
      <v-skeleton-loader v-for="n in 4" :key="n" type="list-item-two-line" />
    </div>

    <template v-else>
      <div v-if="store.items.length === 0" class="flex flex-col items-center gap-2 py-12 text-center text-surface-600">
        <v-icon :icon="icons.notifications" size="48" />
        <p class="m-0 text-h3 text-surface-900">Nothing yet</p>
        <p class="m-0">Updates on requests and comments appear here as they happen.</p>
      </div>

      <p v-else-if="groups.length === 0" class="m-0 py-8 text-center text-surface-600">
        Nothing to show here.
        <button class="font-medium text-primary hover:underline" type="button" @click="clear">Show everything</button>
      </p>

      <div v-else class="flex flex-col">
        <section v-for="group in groups" :key="group.label" :aria-labelledby="`ng-${group.label}`">
          <h2 :id="`ng-${group.label}`" class="m-0 px-4 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-surface-600">{{ group.label }}</h2>

          <ul class="m-0 flex list-none flex-col gap-0.5 p-0">
            <NotificationRow v-for="item in group.items" :key="item.id" :item="item" @open="open" />
          </ul>
        </section>

        <v-btn
          v-if="store.nextBefore"
          class="mt-4 self-center"
          color="primary"
          :loading="store.loading"
          variant="text"
          @click="store.loadMore()"
        >Show older</v-btn>
      </div>
    </template>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { NotificationOut } from '@/api/models'
  import { mdiCheckAll, mdiEmailOutline } from '@mdi/js'
  import { computed, ref } from 'vue'
  import { useRouter } from 'vue-router'
  import { icons } from '@/app/theme/icons'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import { useNotificationsStore } from '@/stores/notifications'
  import NotificationRow from './NotificationRow.vue'
  import { groupByDay } from './notifications'

  // /notifications (AFD §3, PRD NOT-1, NOT-2): the person's own list, newest first by day. Opening
  // one marks it read and goes to what it is about. The list is in memory only; a reload asks
  // again, and a reconnect asks for what came after the newest one it has.
  const store = useNotificationsStore()
  const router = useRouter()

  type View = 'all' | 'unread'
  const view = ref<View>('all')
  const kindKey = ref<string | null>(null)

  const KINDS: Record<string, string> = {
    request: 'Requests', comment: 'Comments', account: 'Accounts', calibration: 'Calibration',
  }

  function kindOf (item: NotificationOut): string {
    return item.type.split('.', 1)[0] ?? 'other'
  }

  const shown = computed(() => store.items.filter(n =>
    (view.value === 'all' || !n.read) && (!kindKey.value || kindOf(n) === kindKey.value)))
  const groups = computed(() => groupByDay(shown.value))

  const views = computed(() => [
    { key: 'all' as const, label: 'All', count: store.items.length },
    { key: 'unread' as const, label: 'Unread', count: store.unread },
  ])
  const kinds = computed(() => {
    const counts = new Map<string, number>()
    for (const item of store.items) {
      counts.set(kindOf(item), (counts.get(kindOf(item)) ?? 0) + 1)
    }
    return [...counts].filter(([key]) => key in KINDS).map(([key, count]) => ({ key, label: KINDS[key] ?? key, count }))
  })

  const subtitle = computed(() => {
    if (!store.loaded) {
      return undefined
    }
    return store.unread > 0 ? `${store.unread} unread. The list keeps the last year.` : 'You’re all caught up. The list keeps the last year.'
  })

  const liveText = computed(() => store.live === 'open' ? 'Live' : (store.live === 'off' ? 'Not connected' : 'Reconnecting…'))
  const liveClass = computed(() => store.live === 'open' ? 'bg-success-container text-on-success-container' : 'bg-warning-container text-on-warning-container')

  function setView (next: View): void {
    view.value = next
  }

  function clear (): void {
    view.value = 'all'
    kindKey.value = null
  }

  async function open (item: NotificationOut): Promise<void> {
    void store.markRead(item.id)
    await router.push(item.link)
  }
</script>
