<template>
  <PageBody :subtitle="subtitle" title="Dashboard">
    <template #actions>
      <v-btn v-if="isClient && canAct" color="primary" :prepend-icon="mdiPlus" :to="{ name: 'request-new' }">Report a problem</v-btn>

      <v-btn
        v-else-if="!isClient"
        :loading="loading"
        :prepend-icon="mdiRefresh"
        variant="outlined"
        @click="reload"
      >Refresh</v-btn>
    </template>

    <div class="flex flex-col gap-5">
      <InstallCard />

      <FeedbackBanner v-if="problem === 'failed'" type="error">
        <div class="flex flex-wrap items-center gap-3">
          <span class="grow">We couldn’t load the figures.</span>
          <v-btn size="small" variant="text" @click="reload">Try again</v-btn>
        </div>
      </FeedbackBanner>

      <AdminDashboardView v-if="view === 'admin'" :data="admin" :loading="loading" :unavailable="unavailable" />
      <TechnicianDashboardView v-else-if="view === 'technician'" :data="technician" :loading="loading" :unavailable="unavailable" />
      <ClientDashboardView v-else :data="client" :loading="loading" :unavailable="unavailable" />
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import { mdiPlus, mdiRefresh } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed } from 'vue'
  import InstallCard from '@/app/pwa/InstallCard.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import { useSessionStore } from '@/stores/session'
  import AdminDashboardView from './AdminDashboardView.vue'
  import ClientDashboardView from './ClientDashboardView.vue'
  import { isAdminView, isClientView, isTechnicianView, ownView } from './dashboard'
  import TechnicianDashboardView from './TechnicianDashboardView.vue'
  import { useDashboard } from './useDashboard'

  // One dashboard per role (AFD §3, PRD SUM-4 to SUM-6): the admin's, which a Viewer sees without
  // the actions, the technician's and the client's. Each is figures from the server, kept a minute
  // there and looked at again here, and never kept on the device.
  const session = useSessionStore()
  const { user, isClient, canAct, roles } = storeToRefs(session)

  const view = computed(() => ownView(roles.value))
  const { data, loading, problem, reload } = useDashboard(() => view.value)
  const unavailable = computed(() => problem.value === 'offline')
  const admin = computed(() => data.value && isAdminView(data.value) ? data.value : null)
  const technician = computed(() => data.value && isTechnicianView(data.value) ? data.value : null)
  const client = computed(() => data.value && isClientView(data.value) ? data.value : null)

  const subtitle = computed(() => {
    const first = (user.value?.name ?? '').split(' ', 1)[0]
    const hello = isClient.value ? 'Welcome' : greeting()
    return `${hello}${first ? `, ${first}` : ''}. These figures update every minute.`
  })

  function greeting (now: Date = new Date()): string {
    const hour = now.getHours()
    if (hour < 12) {
      return 'Good morning'
    }
    return hour < 18 ? 'Good afternoon' : 'Good evening'
  }
</script>
