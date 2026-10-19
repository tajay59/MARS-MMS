<template>
  <ModalSheet
    labelledby="mf-h"
    :max-width="520"
    :model-value="open"
    persistent
    @update:model-value="onToggle"
  >
    <form class="flex flex-col gap-4" novalidate @submit.prevent="save">
      <h2 id="mf-h" class="m-0 text-h2 text-surface-900">{{ model ? `Edit ${model.manufacturer} ${model.model}` : 'Add a sensor model' }}</h2>

      <FeedbackBanner v-if="stale" type="warning">
        <div class="font-semibold">Someone else changed this model.</div>
        <div>Reload to see their changes, then make yours again.</div>
      </FeedbackBanner>

      <FeedbackBanner v-else-if="message" type="error">{{ message }}</FeedbackBanner>

      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FormField id="mf-kind" label="Kind">
          <v-select
            id="mf-kind"
            v-model="values.kind"
            :error-messages="errors.kind"
            item-title="label"
            item-value="value"
            :items="kindOptions"
            name="kind"
          />
        </FormField>

        <FormField id="mf-interval" label="Calibrate every (days, optional)">
          <v-text-field
            id="mf-interval"
            v-model="values.interval"
            autocomplete="off"
            :error-messages="errors.interval"
            inputmode="numeric"
            name="interval"
            placeholder="365"
            suffix="days"
          />
        </FormField>
      </div>

      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FormField id="mf-make" label="Make">
          <v-text-field
            id="mf-make"
            v-model="values.manufacturer"
            autocomplete="off"
            :error-messages="errors.manufacturer"
            maxlength="120"
            name="manufacturer"
          />
        </FormField>

        <FormField id="mf-model" label="Model">
          <v-text-field
            id="mf-model"
            v-model="values.model"
            autocomplete="off"
            :error-messages="errors.model"
            maxlength="120"
            name="model"
          />
        </FormField>
      </div>

      <ParameterField
        id="mf-parameters"
        v-model="values.parameters"
        :error="errors.parameters"
        :suggestions="suggestions"
      />

      <div class="mt-1 flex justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="requestClose">Cancel</v-btn>

        <v-btn v-if="stale" color="primary" variant="outlined" @click="reload">Reload</v-btn>

        <v-btn
          v-else
          color="primary"
          :disabled="model !== null && !dirty"
          :loading="busy"
          type="submit"
        >{{ model ? 'Save' : 'Add model' }}</v-btn>
      </div>
    </form>
  </ModalSheet>

  <DiscardConfirm v-model="askLeave" message="What you typed about this model will be lost." @leave="leave" />
</template>

<script lang="ts" setup>
  import type { ModelField, ModelValues } from './sensorForms'
  import type { SensorModelOut } from '@/api/models'
  import { computed, reactive, ref, watch } from 'vue'
  import { sensorModelsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { focusFirstError } from '@/app/composables/focusFirstError'
  import { useFormDialog } from '@/app/composables/useFormDialog'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import ParameterField from './ParameterField.vue'
  import { emptyModel, kindOptions, modelCreateBody, modelPatchBody, modelProblem, modelValues, validateModel } from './sensorForms'

  // Add or edit a sensor model (PRD SEN-1; approved mock-up "W6 forms"). Online only: nothing here
  // is queued for sync (OFF-10).
  const props = defineProps<{
    /** The model being edited; null to add one. */
    model: SensorModelOut | null
    /** Parameter codes other models use, offered as picks. */
    suggestions: string[]
  }>()

  const emit = defineEmits<{
    saved: [model: SensorModelOut]
    reload: []
  }>()

  const open = defineModel<boolean>({ required: true })

  const values = reactive<ModelValues>(emptyModel())
  const errors = ref<Partial<Record<ModelField, string>>>({})
  const message = ref<string | null>(null)
  const stale = ref(false)
  const busy = ref(false)
  const initial = ref(JSON.stringify(values))

  const dirty = computed(() => JSON.stringify(values) !== initial.value)
  const { askLeave, requestClose, leave } = useFormDialog(open, () => dirty.value)

  watch(open, isOpen => {
    if (!isOpen) {
      return
    }
    Object.assign(values, props.model ? modelValues(props.model) : emptyModel())
    initial.value = JSON.stringify(values)
    errors.value = {}
    message.value = null
    stale.value = false
  }, { immediate: true })

  function onToggle (isOpen: boolean): void {
    if (!isOpen) {
      requestClose()
    }
  }

  function reload (): void {
    emit('reload')
    open.value = false
  }

  async function save (): Promise<void> {
    message.value = null
    errors.value = validateModel(values)
    if (Object.keys(errors.value).length > 0) {
      await focusFirstError()
      return
    }
    const patch = props.model ? modelPatchBody(values, props.model) : null
    if (props.model && !patch) {
      open.value = false
      return
    }
    busy.value = true
    try {
      const saved = props.model && patch
        ? await sensorModelsApi.update(props.model.id, patch)
        : await sensorModelsApi.create(modelCreateBody(values))
      emit('saved', saved)
      open.value = false
    } catch (error) {
      if (error instanceof NetworkError) {
        message.value = 'This needs a connection. It will save when you have signal.'
      } else if (error instanceof ApiError) {
        const problem = modelProblem(error, values)
        if (problem.kind === 'stale') {
          stale.value = true
        } else if (problem.kind === 'fields') {
          errors.value = problem.errors
          message.value = problem.message
          await focusFirstError()
        } else {
          message.value = problem.message
        }
      } else {
        message.value = 'We couldn’t save the model. Try again in a moment.'
      }
    } finally {
      busy.value = false
    }
  }
</script>
