<template>
  <ModalSheet v-model="open" labelledby="ts-reset-h" :max-width="480">
    <div class="flex flex-col gap-4">
      <div class="flex flex-col gap-2">
        <h2 id="ts-reset-h" class="m-0 text-h2 text-surface-900">Reset two-step sign-in for {{ user.name }}?</h2>
        <p class="m-0 text-sm text-surface-900">Use this when {{ first }} has lost their phone and their recovery codes.</p>
      </div>

      <ul class="m-0 flex list-disc flex-col gap-2 pl-5 text-sm text-surface-900">
        <li>{{ first }} is logged out on every device, at once.</li>
        <li>{{ first }} can log in with their password. Two-step sign-in is off until they set it up again.</li>
        <li v-if="isAdmin">They have 7 days to set it up again before it is required.</li>
        <li>This is recorded in the audit log under your name.</li>
      </ul>

      <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="open = false">Cancel</v-btn>
        <v-btn color="error" :loading="busy" @click="submit">Reset two-step sign-in</v-btn>
      </div>
    </div>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { UserOut } from '@/api/models'
  import { computed, ref } from 'vue'
  import { usersApi } from '@/api/auth'
  import { ApiError, NetworkError } from '@/api/problem'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import ModalSheet from '@/components/ModalSheet.vue'

  // Reset someone's two-step sign-in (W22-8). Destructive, so it is a danger button on the final
  // confirm; the API takes no reason (the audit log shows who did it). Never on yourself: the
  // page doesn't offer it, and the server refuses.
  const props = defineProps<{ user: UserOut }>()
  const open = defineModel<boolean>({ required: true })
  const emit = defineEmits<{ reset: [user: UserOut] }>()

  const busy = ref(false)
  const problem = ref<string | null>(null)
  const first = computed(() => props.user.name.split(' ', 1)[0] ?? props.user.name)
  const isAdmin = computed(() => props.user.roles.includes('admin'))

  async function submit (): Promise<void> {
    if (busy.value) {
      return
    }
    busy.value = true
    problem.value = null
    try {
      emit('reset', await usersApi.resetTotp(props.user.id))
      open.value = false
    } catch (error) {
      if (error instanceof NetworkError) {
        problem.value = 'This needs a connection. Try again when you have signal.'
      } else if (error instanceof ApiError && error.code === 'totp_not_enabled') {
        problem.value = `${first.value} has no two-step sign-in to reset. Reload the page.`
      } else {
        problem.value = 'Something went wrong on our side. Try again in a minute.'
      }
    } finally {
      busy.value = false
    }
  }
</script>
