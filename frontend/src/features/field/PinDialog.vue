<template>
  <ModalSheet v-model="open" labelledby="pin-h" :max-width="440" persistent>
    <form class="flex flex-col gap-4" novalidate @submit.prevent="next">
      <h2 id="pin-h" class="m-0 text-h2 text-surface-900">{{ step === 'enter' ? 'Set a PIN for this phone' : 'Enter it again' }}</h2>

      <p class="m-0 text-surface-900">
        {{ step === 'enter'
          ? 'You will use it to open your field work when you have no signal. It stays on this phone and is never sent anywhere.'
          : 'Type the same PIN to check it.' }}
      </p>

      <FormField id="pin" :label="step === 'enter' ? 'PIN' : 'Repeat the PIN'">
        <v-text-field
          id="pin"
          ref="field"
          v-model="value"
          autocomplete="off"
          :error-messages="problem ? [problem] : []"
          inputmode="numeric"
          maxlength="6"
          name="device-pin"
          type="password"
          @update:model-value="problem = ''"
        />
      </FormField>

      <p v-if="step === 'enter'" class="m-0 text-sm text-surface-600">
        4 to 6 digits. Not 1234, 0000 or another easy run. Your phone passcode still protects the data on it.
      </p>

      <div class="flex gap-3">
        <v-btn
          class="grow"
          variant="outlined"
          @click="step === 'enter' ? close() : back()"
        >{{ step === 'enter' ? 'Not now' : 'Back' }}</v-btn>

        <v-btn
          class="grow"
          color="primary"
          :loading="saving"
          type="submit"
        >{{ step === 'enter' ? 'Continue' : 'Save PIN' }}</v-btn>
      </div>
    </form>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import { nextTick, ref, watch } from 'vue'
  import { currentSession } from '@/app/auth/session'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { savePin } from '@/offline/account'
  import { checkPin } from '@/offline/session'

  // Setting the device PIN (AUTH-12, W13-3): once, the first time a technician or admin prepares a
  // visit on this phone, and again from My profile to change it. Two steps, so a slip is caught.
  // Saved only on this phone; nothing is sent to the server.
  const open = defineModel<boolean>({ required: true })
  const emit = defineEmits<{ saved: [], cancel: [] }>()

  const step = ref<'enter' | 'confirm'>('enter')
  const value = ref('')
  const first = ref('')
  const problem = ref('')
  const saving = ref(false)
  const field = ref<{ focus: () => void } | null>(null)

  watch(open, async isOpen => {
    if (isOpen) {
      step.value = 'enter'
      value.value = ''
      first.value = ''
      problem.value = ''
      await nextTick()
      field.value?.focus()
    }
  })

  function close (): void {
    open.value = false
    emit('cancel')
  }

  function back (): void {
    step.value = 'enter'
    value.value = ''
    problem.value = ''
  }

  async function next (): Promise<void> {
    if (step.value === 'enter') {
      const verdict = checkPin(value.value)
      if (verdict === 'format') {
        problem.value = 'Use 4 to 6 digits.'
      } else if (verdict === 'weak') {
        problem.value = 'That PIN is too easy to guess. Avoid repeated digits and runs like 1234.'
      } else {
        first.value = value.value
        value.value = ''
        step.value = 'confirm'
        await nextTick()
        field.value?.focus()
      }
      return
    }
    if (value.value !== first.value) {
      step.value = 'enter'
      value.value = ''
      first.value = ''
      problem.value = 'The two PINs are different. Start again.'
      return
    }
    const session = currentSession()
    if (!session) {
      problem.value = 'This needs a connection. Log in with signal, then set the PIN.'
      return
    }
    saving.value = true
    try {
      await savePin(session, first.value)
      open.value = false
      emit('saved')
    } catch {
      problem.value = 'The PIN could not be saved on this phone. Try again.'
    } finally {
      saving.value = false
    }
  }
</script>
