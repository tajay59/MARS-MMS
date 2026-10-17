<template>
  <PageBody :subtitle="greeting" title="Dashboard">
    <template v-if="isClient && canAct" #actions>
      <v-btn color="primary" :prepend-icon="mdiPlus" :to="{ name: 'request-new' }">Report a problem</v-btn>
    </template>

    <!-- The pane: what needs this person now. Filters join it with the stations (phase 2). -->
    <PaneContent>
      <section aria-labelledby="attention-h" class="flex flex-col gap-1 px-3">
        <h3 id="attention-h" class="m-0 px-2 pb-1 text-sm font-semibold text-surface-900">Needs your attention</h3>

        <router-link
          v-if="isAdmin"
          class="flex items-center gap-3 rounded-card p-3 hover:bg-surface-100"
          :to="{ name: 'admin-registrations' }"
        >
          <span class="flex min-w-0 grow flex-col">
            <span class="font-medium text-surface-900">Registrations pending</span>
            <span class="text-sm text-surface-600">Check and approve new accounts</span>
          </span>

          <span class="text-h2 tabular-nums text-surface-900">{{ registrations.pending ?? '—' }}</span>
        </router-link>

        <p v-else class="m-0 px-2 text-sm text-surface-600">Nothing needs you right now.</p>
      </section>
    </PaneContent>

    <section class="flex max-w-2xl flex-col gap-2">
      <h2 class="m-0 text-h3 text-surface-900">{{ next.title }}</h2>
      <p class="m-0 text-surface-600">{{ next.text }}</p>
    </section>
  </PageBody>
</template>

<script lang="ts" setup>
  import { mdiPlus } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, onMounted } from 'vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import { useRegistrationsStore } from '@/stores/registrations'
  import { useSessionStore } from '@/stores/session'

  // One dashboard per role (AFD §3). Phase 1 has the admin's registrations widget (J1 step 3);
  // each role's widgets arrive with the features they count.
  const session = useSessionStore()
  const { user, isAdmin, isClient, canAct } = storeToRefs(session)
  const registrations = useRegistrationsStore()

  const greeting = computed(() => `Signed in as ${user.value?.name ?? ''}`)
  const next = computed(() => isClient.value
    ? { title: 'Your stations and requests', text: 'Station pages arrive in phase 2 and reporting a problem in phase 3.' }
    : { title: 'Your work', text: 'The queue, your visits and the station map arrive in phases 2 and 3.' })

  onMounted(() => {
    if (isAdmin.value) {
      void registrations.refresh()
    }
  })
</script>
