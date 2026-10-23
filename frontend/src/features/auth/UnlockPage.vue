<template>
  <AuthCard v-if="session.unlockState === 'ready' && session.lockedProfile" lead="You have no signal. Enter the PIN you set on this phone." title="Unlock your field work">
    <div class="flex items-center gap-3 rounded-card bg-surface-50 p-3">
      <UserAvatar :name="session.lockedProfile.name" :seed="session.lockedProfile.user_id" size="sm" />

      <div class="min-w-0">
        <p class="m-0 truncate font-semibold text-surface-900">{{ session.lockedProfile.name }}</p>
        <p class="m-0 text-sm text-surface-600">{{ roleLabel(session.lockedProfile.roles) }}</p>
      </div>
    </div>

    <div aria-live="polite" class="empty:hidden">
      <FeedbackBanner v-if="failure" type="error">
        <strong class="block">That PIN is not right.</strong>
        {{ left === 1 ? '1 try left.' : `${left} tries left.` }} After that, offline unlock turns off until you log in with signal.
      </FeedbackBanner>
    </div>

    <PinPad v-model="pin" :disabled="busy" :error="Boolean(failure)" @submit="submit" />

    <div v-if="busy" aria-live="polite" class="flex flex-col gap-2" role="status">
      <v-progress-linear height="6" indeterminate rounded />
      <p class="m-0 text-center text-sm text-surface-600">Checking your PIN. This takes a second or two on purpose: it keeps the PIN hard to guess.</p>
    </div>

    <v-btn
      block
      color="primary"
      :disabled="pin.length < 4 || busy"
      type="button"
      @click="submit"
    >Unlock</v-btn>

    <p class="m-0 text-center text-sm text-surface-600">
      Forgot it? Log in when you have signal. Your work stays on this phone.
    </p>
  </AuthCard>

  <AuthCard v-else-if="session.locked" :title="session.unlockState === 'expired' ? 'Your offline session has ended' : 'Offline unlock is turned off'">
    <FeedbackBanner type="warning">
      Connect to the internet and log in to continue. Your work is saved on this phone.
    </FeedbackBanner>

    <ul class="m-0 flex list-none flex-col gap-3 p-0 text-surface-900" role="list">
      <li class="flex items-start gap-3">
        <v-icon class="mt-0.5 text-success" :icon="mdiCheck" size="20" />
        Nothing was deleted. Visits you prepared and anything you recorded are still here.
      </li>

      <li class="flex items-start gap-3">
        <v-icon class="mt-0.5 text-success" :icon="mdiCheck" size="20" />
        It syncs after you log in with signal.
      </li>
    </ul>

    <v-btn block color="primary" :to="{ name: 'login', query: { next: nextPath } }">Log in</v-btn>
  </AuthCard>
</template>

<script lang="ts" setup>
  import { mdiCheck } from '@mdi/js'
  import { computed, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { safeNext } from '@/app/router/next'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PinPad from '@/components/PinPad.vue'
  import UserAvatar from '@/components/UserAvatar.vue'
  import { roleLabel } from '@/features/requests/queue'
  import { unlock } from '@/offline/session'
  import { useSessionStore } from '@/stores/session'
  import AuthCard from './AuthCard.vue'

  // AUTH-12, AFD J6 step 0. The app started with no signal and this phone has an offline session:
  // the device PIN opens the field data. The failure count is saved before each check (see
  // offline/session.ts), so closing the app does not give a try back.
  const route = useRoute()
  const router = useRouter()
  const session = useSessionStore()

  const pin = ref('')
  const busy = ref(false)
  const failure = ref(false)
  const left = ref(0)

  const nextPath = computed(() => safeNext(route.query.next) ?? undefined)

  // Where a PIN lands when nothing else was asked for: the field pages that work with no signal
  const DEFAULT_PAGE = { name: 'sync' } as const

  async function submit (): Promise<void> {
    if (busy.value || pin.value.length < 4) {
      return
    }
    busy.value = true
    failure.value = false
    try {
      const result = await unlock(pin.value)
      pin.value = ''
      if (result.ok) {
        session.unlockOffline(result.profile)
        await router.replace(nextPath.value ?? DEFAULT_PAGE)
        return
      }
      switch (result.reason) {
        case 'wrong': {
          failure.value = true
          left.value = result.left
          break
        }
        case 'locked': {
          session.disableUnlock()
          break
        }
        default: {
          // none, expired or disabled since the page opened
          session.unlockState = result.reason === 'none' ? 'expired' : result.reason
        }
      }
    } finally {
      busy.value = false
    }
  }

  // Signal came back while waiting (the store signs in with the refresh cookie): carry on
  watch(() => session.user && !session.offline && !session.locked, async signedIn => {
    if (signedIn) {
      await router.replace(nextPath.value ?? { name: 'dashboard' })
    }
  })
</script>
