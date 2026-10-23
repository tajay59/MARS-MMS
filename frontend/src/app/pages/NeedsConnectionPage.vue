<template>
  <PageBody title="Needs a connection">
    <div class="flex grow flex-col justify-center gap-3 p-3 md:p-0 md:py-8">
      <ScanCard :icon="mdiCloudOffOutline" title="This needs a connection" tone="neutral">
        Requests, approvals and reports work online. The visits you prepared still work with no signal.
        <template #actions>
          <v-btn
            block
            color="primary"
            size="large"
            :to="{ name: 'sync' }"
          >Open Sync</v-btn>

          <v-btn
            block
            :loading="trying"
            size="large"
            variant="text"
            @click="tryAgain"
          >Try again</v-btn>
        </template>
      </ScanCard>
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import { mdiCloudOffOutline } from '@mdi/js'
  import { ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { safeNext } from '@/app/router/next'
  import PageBody from '@/components/PageBody.vue'
  import ScanCard from '@/features/scan/ScanCard.vue'
  import { useSessionStore } from '@/stores/session'

  // Where a page that needs the server sends someone who unlocked with the PIN and has no signal
  // (OFF-10, AFD §5.2). Try again asks for a session; once the signal is back the page they wanted
  // opens, and until then they stay here.
  const route = useRoute()
  const router = useRouter()
  const session = useSessionStore()
  const trying = ref(false)

  async function tryAgain (): Promise<void> {
    trying.value = true
    try {
      await session.reconnect()
      if (!session.offline) {
        await router.replace(safeNext(route.query.from) ?? { name: 'dashboard' })
      }
    } finally {
      trying.value = false
    }
  }
</script>
