<template>
  <!-- Finalize: board 5 of the W16 sheet -->
  <ModalSheet v-model="finalizing" labelledby="fz-h" max-width="460" persistent>
    <div class="flex flex-col gap-4">
      <h2 id="fz-h" class="m-0 text-h3 text-surface-900">Finalize this report?</h2>
      <p class="m-0 text-surface-800">The visit’s boards lock and the report becomes final. To change it afterwards, an admin has to reopen it for correction.</p>
      <FeedbackBanner v-if="signedBy" type="info">{{ signedBy }} If this was the last visit, the client is asked to review the work.</FeedbackBanner>
      <FeedbackBanner v-if="failure" type="error">{{ failure }}</FeedbackBanner>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn :disabled="busy" variant="outlined" @click="finalizing = false">Not yet</v-btn>
        <v-btn color="primary" :loading="busy" @click="emit('finalize')">Finalize</v-btn>
      </div>
    </div>
  </ModalSheet>

  <!-- Reopen for correction: admins only -->
  <ModalSheet v-model="reopening" labelledby="ro-h" max-width="480" persistent>
    <form class="flex flex-col gap-4" novalidate @submit.prevent="submitReopen">
      <h2 id="ro-h" class="m-0 text-h3 text-surface-900">Reopen for correction</h2>
      <p class="m-0 text-surface-800">This makes version {{ version + 1 }} as a draft. Version {{ version }} stays and is marked Superseded. The boards unlock, and the report must be signed again.</p>
      <FeedbackBanner v-if="failure" type="error">{{ failure }}</FeedbackBanner>

      <FormField id="ro-reason" label="Reason">
        <v-textarea
          id="ro-reason"
          v-model="reason"
          auto-grow
          :counter="500"
          :error-messages="reasonError"
          name="reason"
          rows="3"
        />
      </FormField>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn :disabled="busy" variant="outlined" @click="reopening = false">Cancel</v-btn>
        <v-btn color="error" :loading="busy" type="submit">Reopen</v-btn>
      </div>
    </form>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import { ref, watch } from 'vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'

  // The two confirmations of the report page (W17, RPT-5, RPT-6). The wording is from boards 5 and 6
  // of the W16 sheet. Both need a connection; neither keeps anything on the device.
  defineProps<{
    version: number
    busy: boolean
    failure: string | null
    /** "Signed by Devon Brown on 5 Oct 2026, 12:03 EST." */
    signedBy: string
  }>()

  const emit = defineEmits<{ finalize: [], reopen: [reason: string] }>()
  const finalizing = defineModel<boolean>('finalizing', { required: true })
  const reopening = defineModel<boolean>('reopening', { required: true })

  const reason = ref('')
  const reasonError = ref('')

  watch(reopening, isOpen => {
    if (isOpen) {
      reason.value = ''
      reasonError.value = ''
    }
  })

  function submitReopen (): void {
    const clean = reason.value.split(/\s+/).filter(Boolean).join(' ')
    if (clean.length < 5 || clean.length > 500) {
      reasonError.value = 'Give a reason of 5 to 500 characters.'
      document.querySelector<HTMLTextAreaElement>('#ro-reason')?.focus()
      return
    }
    reasonError.value = ''
    emit('reopen', clean)
  }
</script>
