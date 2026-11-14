<template>
  <div v-if="banner" class="shrink-0 px-4 pt-4 md:px-8 md:pt-6">
    <FeedbackBanner :type="banner.type">
      <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <span><b class="font-semibold">{{ banner.lead }}</b> {{ banner.rest }}</span>

        <router-link
          class="inline-flex min-h-6 items-center font-semibold underline"
          :to="{ name: 'profile', hash: '#two-step' }"
        >Set up now</router-link>
      </div>
    </FeedbackBanner>
  </div>

  <!-- After logging in with a recovery code: stays until dismissed, like other warnings -->
  <v-snackbar
    v-model="noticeOpen"
    location="bottom"
    :timeout="-1"
  >
    <span class="flex items-start gap-2.5">
      <v-icon :icon="mdiAlertOutline" size="20" />

      <span class="min-w-0">
        <b class="font-semibold">You used a recovery code. {{ recoveryNotice }} {{ recoveryNotice === 1 ? 'is' : 'are' }} left.</b>
        Make new ones in My profile before they run out.
      </span>
    </span>

    <template #actions>
      <v-btn color="inverse-primary" :to="{ name: 'profile', hash: '#two-step' }" variant="text" @click="dismiss">My profile</v-btn>
      <v-btn color="inverse-primary" variant="text" @click="dismiss">Dismiss</v-btn>
    </template>
  </v-snackbar>
</template>

<script lang="ts" setup>
  import { mdiAlertOutline } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed } from 'vue'
  import { setupBanner } from '@/features/auth/twoStep/twoStep'
  import { useSessionStore } from '@/stores/session'
  import FeedbackBanner from './FeedbackBanner.vue'

  // Two-step sign-in notices that follow a person through the app (W22, "banner on all pages"): the
  // nudge while their role needs it and they have none, and the recovery codes left after using one.
  const session = useSessionStore()
  const { mfaRequiredBy, recoveryNotice, user } = storeToRefs(session)

  const banner = computed(() => mfaRequiredBy.value
    ? setupBanner(mfaRequiredBy.value, new Date(), user.value?.time_zone)
    : null)

  const noticeOpen = computed({
    get: () => recoveryNotice.value !== null,
    set: open => {
      if (!open) {
        session.dismissRecoveryNotice()
      }
    },
  })

  function dismiss (): void {
    session.dismissRecoveryNotice()
  }
</script>
