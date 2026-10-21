<template>
  <ModalSheet v-model="open" labelledby="cv-h" max-width="460" persistent>
    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <h2 id="cv-h" class="m-0 text-h2 text-surface-900">Cancel visit {{ visit.ref }}?</h2>

      <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

      <FormField id="cv-reason" label="Reason (optional)">
        <v-textarea
          id="cv-reason"
          v-model="reason"
          auto-grow
          name="reason"
          placeholder="For example, a storm warning for Thursday"
          rows="2"
        />
      </FormField>

      <p class="m-0 text-sm text-surface-600">
        The client and everyone attending are told. If no other visit is planned, the request goes back to Assigned.
      </p>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="requestClose">Keep it</v-btn>
        <v-btn color="error" :loading="busy" type="submit">Cancel visit</v-btn>
      </div>
    </form>

    <DiscardConfirm v-model="askLeave" message="What you typed will be lost." @leave="leave" />
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { VisitOut } from '@/api/models'
  import { ref, watch } from 'vue'
  import { visitsApi } from '@/api/operations'
  import { useFormDialog } from '@/app/composables/useFormDialog'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { failureOf } from './failures'

  // Cancel visit (PRD VIS-2): a planned visit, with a reason if there is one.
  const props = defineProps<{ visit: Pick<VisitOut, 'id' | 'ref'> }>()

  const emit = defineEmits<{ done: [visit: VisitOut], changed: [] }>()
  const open = defineModel<boolean>({ required: true })

  const reason = ref('')
  const problem = ref<string | null>(null)
  const busy = ref(false)

  const { askLeave, requestClose, leave } = useFormDialog(open, () => reason.value.trim() !== '' && !busy.value)

  watch(open, isOpen => {
    if (isOpen) {
      reason.value = ''
      problem.value = null
    }
  }, { immediate: true })

  async function submit (): Promise<void> {
    if (busy.value) {
      return
    }
    busy.value = true
    problem.value = null
    try {
      const done = await visitsApi.cancel(props.visit.id, reason.value.trim())
      open.value = false
      emit('done', done)
    } catch (error) {
      const failure = failureOf(error, 'We couldn’t cancel the visit. Try again in a moment.')
      problem.value = failure.message
      if (failure.reload) {
        emit('changed')
      }
    } finally {
      busy.value = false
    }
  }
</script>
