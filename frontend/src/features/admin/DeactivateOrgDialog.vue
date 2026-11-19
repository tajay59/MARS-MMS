<template>
  <ModalSheet v-model="open" labelledby="org-off-h" :max-width="520">
    <div class="flex flex-col gap-4">
      <div class="flex flex-col gap-2">
        <h2 id="org-off-h" class="m-0 text-h2 text-surface-900">Deactivate {{ org.name }}?</h2>
        <p class="m-0 text-body text-surface-900">{{ who }}</p>
        <p class="m-0 text-sm text-surface-600">Nothing is deleted. Its stations, requests, reports and history stay as they are, and staff can still see them.</p>
      </div>

      <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="open = false">Cancel</v-btn>
        <v-btn color="error" :loading="busy" @click="submit">Deactivate</v-btn>
      </div>
    </div>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { OrgOut } from '@/api/models'
  import { computed, ref } from 'vue'
  import { orgsApi } from '@/api/auth'
  import { ApiError, NetworkError } from '@/api/problem'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import ModalSheet from '@/components/ModalSheet.vue'

  // ORG-4: the final confirm, so the danger button is here only. No reason is asked: the audit
  // log records who did it and when (approved mock-up, "AWS-MMS Organizations screen").
  const props = defineProps<{ org: OrgOut, people: number }>()
  const open = defineModel<boolean>({ required: true })
  const emit = defineEmits<{ done: [org: OrgOut] }>()

  const busy = ref(false)
  const problem = ref<string | null>(null)

  const who = computed(() => {
    if (props.people === 0) {
      return 'Nobody can sign in for it until you reactivate it.'
    }
    const them = props.people === 1 ? 'Its 1 person is' : `Its ${props.people} people are`
    return `${them} signed out now and can’t sign in until you reactivate it.`
  })

  async function submit (): Promise<void> {
    if (busy.value) {
      return
    }
    busy.value = true
    problem.value = null
    try {
      emit('done', await orgsApi.update(props.org.id, { version: props.org.version, status: 'inactive' }))
      open.value = false
    } catch (error) {
      if (error instanceof NetworkError) {
        problem.value = 'This needs a connection. Try again when you have signal.'
      } else if (error instanceof ApiError && error.code === 'version_conflict') {
        problem.value = 'Someone else changed this organization. Close this, reload the page and try again.'
      } else {
        problem.value = 'Something went wrong on our side. Try again in a minute.'
      }
    } finally {
      busy.value = false
    }
  }
</script>
