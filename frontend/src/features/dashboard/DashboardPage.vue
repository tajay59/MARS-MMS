<template>
  <PageBody :subtitle="greeting" title="Dashboard">
    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <router-link
        v-if="isAdmin"
        class="group rounded-card border border-surface-200 bg-surface p-6 hover:border-primary"
        :to="{ name: 'admin-registrations' }"
      >
        <p class="m-0 text-label text-surface-600">Registrations pending</p>
        <p class="m-0 mt-2 text-kpi tabular-nums text-surface-900">{{ registrations.pending ?? '—' }}</p>
        <p class="m-0 mt-2 text-sm font-medium text-primary group-hover:underline">Check and approve</p>
      </router-link>

      <v-card class="flex flex-col gap-2 border border-surface-200 p-6">
        <h2 class="m-0 text-h3 text-surface-900">{{ next.title }}</h2>
        <p class="m-0 text-surface-600">{{ next.text }}</p>
      </v-card>
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import { storeToRefs } from 'pinia'
  import { computed, onMounted } from 'vue'
  import PageBody from '@/components/PageBody.vue'
  import { useRegistrationsStore } from '@/stores/registrations'
  import { useSessionStore } from '@/stores/session'

  // One dashboard per role (AFD §3). Phase 1 has the admin's registrations widget (J1 step 3);
  // each role's widgets arrive with the features they count.
  const session = useSessionStore()
  const { user, isAdmin, isClient } = storeToRefs(session)
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
