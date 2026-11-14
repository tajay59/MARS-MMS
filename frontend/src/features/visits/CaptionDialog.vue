<template>
  <ModalSheet v-model="open" labelledby="mc-h" :max-width="460" persistent>
    <form class="flex flex-col gap-4" novalidate @submit.prevent="save">
      <h2 id="mc-h" class="m-0 text-h2 text-surface-900">Caption</h2>

      <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

      <FormField id="mc-caption" label="What the picture shows (optional)">
        <v-textarea
          id="mc-caption"
          v-model="caption"
          auto-grow
          counter="300"
          :error-messages="error"
          maxlength="300"
          name="caption"
          placeholder="For example, enclosure door, water marks inside"
          rows="2"
        />
      </FormField>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="requestClose">Cancel</v-btn>
        <v-btn color="primary" :disabled="!dirty" :loading="busy" type="submit">Save</v-btn>
      </div>
    </form>

    <DiscardConfirm v-model="askLeave" message="What you typed will be lost." @leave="leave" />
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { BoardElement, BoardMedia } from '@/api/models'
  import { computed, ref, watch } from 'vue'
  import { useFormDialog } from '@/app/composables/useFormDialog'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { board } from './local/gateway'
  import { mediaFailure } from './media'

  // The caption of one photo or video on an element of a station's board (PRD VIS-5). Empty clears it.
  const props = defineProps<{
    visitId: string
    stationId: string
    elementId: string
    item: BoardMedia | null
  }>()

  const emit = defineEmits<{ done: [element: BoardElement] }>()
  const open = defineModel<boolean>({ required: true })

  const caption = ref('')
  const error = ref<string | null>(null)
  const problem = ref<string | null>(null)
  const busy = ref(false)

  const dirty = computed(() => caption.value.trim() !== (props.item?.caption ?? ''))
  const { askLeave, requestClose, leave } = useFormDialog(open, () => dirty.value && !busy.value)

  watch(open, isOpen => {
    if (isOpen) {
      caption.value = props.item?.caption ?? ''
      error.value = null
      problem.value = null
    }
  }, { immediate: true })

  async function save (): Promise<void> {
    if (busy.value || !props.item) {
      return
    }
    const text = caption.value.trim()
    if (text.length > 300) {
      error.value = 'A caption can be up to 300 characters.'
      return
    }
    busy.value = true
    problem.value = null
    try {
      const element = await board.changeMedia(props.visitId, props.stationId, props.elementId, props.item.media_id, { caption: text || null })
      open.value = false
      emit('done', element)
    } catch (error_) {
      problem.value = mediaFailure(error_, 'We couldn’t save the caption. Try again in a moment.')
    } finally {
      busy.value = false
    }
  }
</script>
