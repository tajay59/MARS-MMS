<template>
  <section
    aria-labelledby="ts-h"
    class="flex scroll-mt-4 flex-col gap-4 border-t border-surface-200 pt-6 first:border-t-0 first:pt-0"
  >
    <div class="flex items-center justify-between gap-3">
      <h2 id="ts-h" class="m-0 text-h3 text-surface-900">Two-step sign-in</h2>

      <span
        class="inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium"
        :class="on ? 'bg-success-container text-on-success-container' : 'bg-surface-100 text-surface-900'"
      >
        <v-icon :icon="on ? mdiCheck : mdiCircleOutline" size="14" />
        {{ on ? 'On' : (required ? 'Not set up' : 'Off') }}
      </span>
    </div>

    <!-- Off -->
    <template v-if="!on">
      <FeedbackBanner v-if="overdue" type="error">
        You’ll need it the next time you log in. Set it up now so you’re not locked out.
      </FeedbackBanner>

      <p class="m-0 text-surface-900">
        A 6-digit code from an app on your phone, as well as your password, every time you log in.
        <template v-if="required"><b class="font-semibold">Required for admins.</b></template>
        <template v-else>Optional. Offline unlock with your PIN is not affected.</template>
      </p>

      <p v-if="required && deadline" class="m-0 text-sm text-surface-600">
        Any authenticator app works, including the one built into your phone’s password manager. You have until {{ deadline }}.
      </p>

      <div><v-btn variant="outlined" @click="enrolOpen = true">{{ required ? 'Set up two-step sign-in' : 'Turn on' }}</v-btn></div>
    </template>

    <!-- On -->
    <template v-else>
      <p class="m-0 text-surface-900">
        Two-step sign-in is on.
        <span class="font-mono text-sm">{{ left }}</span> {{ left === 1 ? 'recovery code' : 'recovery codes' }} left.
        <template v-if="required"> Required for admins, so it can’t be turned off.</template>
      </p>

      <FeedbackBanner v-if="left <= 2" type="warning">
        <b class="font-semibold">{{ left }} recovery {{ left === 1 ? 'code' : 'codes' }} left.</b> Make new ones before they run out.
      </FeedbackBanner>

      <div class="flex flex-wrap gap-2">
        <v-btn variant="outlined" @click="open('codes')">Make new recovery codes</v-btn>
        <v-btn v-if="!required" class="text-primary" variant="text" @click="open('off')">Turn off</v-btn>
      </div>

      <p v-if="required" class="m-0 text-sm text-surface-600">If you lose your phone and your codes, another admin can reset this for you.</p>
    </template>

    <TwoStepEnrolDialog v-model="enrolOpen" @changed="emit('changed')" />
    <TwoStepProofDialog v-model="proofOpen" :mode="proofMode" @changed="emit('changed')" />
  </section>
</template>

<script lang="ts" setup>
  import { mdiCheck, mdiCircleOutline } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, ref } from 'vue'
  import { formatDate } from '@/app/format'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { useSessionStore } from '@/stores/session'
  import TwoStepEnrolDialog from './TwoStepEnrolDialog.vue'
  import TwoStepProofDialog from './TwoStepProofDialog.vue'

  // "Two-step sign-in" on My profile, for staff (W22-7). Clients can't use it. Which roles need it
  // is the server's rule; admins need it by default, and the server refuses to turn it off for a role that does.
  const emit = defineEmits<{ changed: [] }>()
  const session = useSessionStore()
  const { user, mfaRequiredBy } = storeToRefs(session)

  const on = computed(() => user.value?.totp_enabled === true)
  const left = computed(() => user.value?.recovery_codes_left ?? 0)
  const required = computed(() => user.value?.roles.includes('admin') === true)
  const overdue = computed(() => mfaRequiredBy.value !== null && new Date(mfaRequiredBy.value).getTime() <= Date.now())
  const deadline = computed(() => mfaRequiredBy.value && !overdue.value ? formatDate(mfaRequiredBy.value, user.value?.time_zone) : null)

  const enrolOpen = ref(false)
  const proofOpen = ref(false)
  const proofMode = ref<'off' | 'codes'>('off')

  function open (mode: 'off' | 'codes'): void {
    proofMode.value = mode
    proofOpen.value = true
  }
</script>
