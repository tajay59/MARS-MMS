<template>
  <ModalSheet v-model="open" labelledby="rj-h" max-width="480" persistent>
    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <div>
        <h2 id="rj-h" class="m-0 text-h3 text-surface-900">Send the work back</h2>
        <p class="m-0 mt-1 text-sm text-surface-700">The same technicians get the request again, with your reason. You can review it again when they finish.</p>
      </div>

      <FeedbackBanner v-if="failure" :type="failure.tone === 'warning' ? 'warning' : 'error'">
        <b class="font-semibold">{{ failure.title }}</b> {{ failure.text }}
      </FeedbackBanner>

      <FormField id="rj-reason" label="Reason">
        <v-textarea
          id="rj-reason"
          v-model="reason"
          auto-grow
          autocomplete="off"
          :error-messages="error"
          :maxlength="REASON_MAX + 200"
          name="reason"
          placeholder="Say what is wrong, so they know what to do"
          rows="3"
        />

        <template #aside>
          <span class="text-xs tabular-nums text-surface-600">{{ reasonCount(reason) }}</span>
        </template>
      </FormField>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn :disabled="busy" variant="outlined" @click="open = false">Cancel</v-btn>
        <v-btn color="primary" :loading="busy" type="submit">Send</v-btn>
      </div>
    </form>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { Notice } from './review'
  import { ref, watch } from 'vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { REASON_MAX, reasonCount, reasonProblem } from './review'

  // Send the work back (PRD REQ-13; W18 board 2): only the reason is asked for. The technicians and
  // the admins read it. The text lives in this dialog until the server has answered.
  defineProps<{ busy: boolean, failure: Notice | null }>()
  const emit = defineEmits<{ send: [reason: string] }>()
  const open = defineModel<boolean>({ required: true })

  const reason = ref('')
  const error = ref<string | null>(null)

  watch(open, isOpen => {
    if (isOpen) {
      reason.value = ''
      error.value = null
    }
  })

  function submit (): void {
    error.value = reasonProblem(reason.value)
    if (!error.value) {
      emit('send', reason.value.trim())
    }
  }
</script>
