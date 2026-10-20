<template>
  <ModalSheet v-model="open" labelledby="rd-h" max-width="460" persistent>
    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <h2 id="rd-h" class="m-0 text-h2 text-surface-900">{{ mode === 'deny' ? 'Deny' : 'Cancel' }} request {{ request.ref }}?</h2>

      <p class="m-0 text-surface-700">
        {{ mode === 'deny'
          ? 'The client sees your reason. A denied request can’t be reopened.'
          : 'This stops the request. You can’t undo it, but you can make a new one.' }}
      </p>

      <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

      <FormField id="rd-reason" :label="reasonRequired ? 'Reason' : 'Reason (optional)'">
        <v-textarea
          id="rd-reason"
          v-model="reason"
          auto-grow
          :error-messages="error"
          name="reason"
          :placeholder="placeholder"
          rows="3"
        />
      </FormField>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="requestClose">Keep request</v-btn>
        <v-btn color="error" :loading="busy" type="submit">{{ mode === 'deny' ? 'Deny' : 'Cancel' }} request</v-btn>
      </div>
    </form>

    <DiscardConfirm v-model="askLeave" message="What you typed will be lost." @leave="leave" />
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { RequestDetail } from '@/api/models'
  import { computed, ref, watch } from 'vue'
  import { requestsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { useFormDialog } from '@/app/composables/useFormDialog'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'

  // Deny (PRD REQ-6: the reason is required, and the client sees it) and Cancel request (REQ-11:
  // a reason from Scheduled on, optional before). The server decides; this asks for what it needs.
  const props = defineProps<{
    mode: 'deny' | 'cancel'
    request: Pick<RequestDetail, 'id' | 'ref'>
    reasonRequired: boolean
  }>()

  const emit = defineEmits<{ done: [request: RequestDetail], changed: [] }>()
  const open = defineModel<boolean>({ required: true })

  const reason = ref('')
  const error = ref<string | null>(null)
  const problem = ref<string | null>(null)
  const busy = ref(false)

  const placeholder = computed(() => props.mode === 'deny'
    ? 'Say why, so the client knows what to do next'
    : (props.reasonRequired ? 'Say why it is being cancelled' : 'For example, the fault fixed itself'))

  const { askLeave, requestClose, leave } = useFormDialog(open, () => reason.value.trim() !== '' && !busy.value)

  watch(open, isOpen => {
    if (isOpen) {
      reason.value = ''
      error.value = null
      problem.value = null
    }
  })

  async function submit (): Promise<void> {
    error.value = null
    problem.value = null
    const text = reason.value.trim()
    if ((props.mode === 'deny' || props.reasonRequired) && !text) {
      error.value = 'Say why'
      return
    }
    busy.value = true
    try {
      const done = props.mode === 'deny'
        ? await requestsApi.deny(props.request.id, text)
        : await requestsApi.cancel(props.request.id, text)
      open.value = false
      emit('done', done)
    } catch (error_) {
      if (error_ instanceof NetworkError) {
        problem.value = 'This needs a connection. What you typed is still here; try again when you have signal.'
      } else if (error_ instanceof ApiError && (error_.code === 'request_changed' || error_.code === 'bad_transition')) {
        problem.value = 'Someone else just changed this request. Close this and reload to see it.'
        emit('changed')
      } else if (error_ instanceof ApiError && error_.field === 'reason') {
        error.value = error_.detail
      } else {
        problem.value = error_ instanceof ApiError && error_.status < 500 ? error_.detail : 'We couldn’t do that. Try again in a moment.'
      }
    } finally {
      busy.value = false
    }
  }
</script>
