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

      <FeedbackBanner v-if="!online" :icon="mdiWifiOff" type="warning">
        <div class="font-semibold">You’re offline</div>
        <div>Saving needs a connection. What you’ve typed stays here until you’re back online.</div>
      </FeedbackBanner>

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

      <FeedbackBanner v-if="duplicate" type="error">
        <span class="font-semibold">Already in the catalogue:</span>
        {{ values.manufacturer.trim() }} {{ values.model.trim() }}. Change the make or model, or find it in the list.
      </FeedbackBanner>

      <ParameterField
        id="mf-parameters"
        v-model="values.parameters"
        :error="errors.parameters"
        :suggestions="suggestions"
      />

      <SpecsField v-model="values.specs" :error="errors.specs" />

      <PhotoStager
        id="mf-photos"
        v-model="photos"
        :disabled="busy"
        :states="photoStates"
      />

      <div class="mt-1 flex justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="requestClose">{{ modelSaved ? 'Close' : 'Cancel' }}</v-btn>

        <v-btn v-if="stale" color="primary" variant="outlined" @click="reload">Reload</v-btn>

        <v-btn
          v-else
          color="primary"
          :disabled="!online || (model !== null && !dirty)"
          :loading="busy"
          type="submit"
        >{{ submitLabel }}</v-btn>
      </div>
    </form>
  </ModalSheet>

  <DiscardConfirm v-model="askLeave" message="What you typed about this model will be lost." @leave="leave" />
</template>

<script lang="ts" setup>
  import type { ModelField, ModelValues } from './sensorForms'
  import type { SensorModelOut } from '@/api/models'
  import { mdiWifiOff } from '@mdi/js'
  import { computed, reactive, ref, watch } from 'vue'
  import { documentsApi, sensorModelsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { focusFirstError } from '@/app/composables/focusFirstError'
  import { useFormDialog } from '@/app/composables/useFormDialog'
  import { useOnline } from '@/app/composables/useOnline'
  import { useUploads } from '@/app/composables/useUpload'
  import { newId } from '@/app/ids'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { PHOTO_TYPE, titleFromFilename } from '@/features/stations/documents'
  import ParameterField from './ParameterField.vue'
  import PhotoStager from './PhotoStager.vue'
  import { emptyModel, kindOptions, modelCreateBody, modelPatchBody, modelProblem, modelValues, validateModel } from './sensorForms'
  import SpecsField from './SpecsField.vue'

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
    /** Photos were added to a model, so its gallery has changed. */
    photos: [modelId: string]
    reload: []
  }>()

  const open = defineModel<boolean>({ required: true })

  const values = reactive<ModelValues>(emptyModel())
  const errors = ref<Partial<Record<ModelField, string>>>({})
  const message = ref<string | null>(null)
  const stale = ref(false)
  const busy = ref(false)
  const initial = ref(JSON.stringify(values))
  const online = useOnline()
  const uploads = useUploads()

  // The model is made first, then each photo is sent and filed against it. If a photo fails the
  // model stays saved: this remembers it, so "Try again" only repeats the photos.
  const duplicate = ref(false)
  const photos = ref<File[]>([])
  const photoStates = ref<Record<string, string>>({})
  const modelSaved = ref<SensorModelOut | null>(null)
  // One document ID per photo: a retry after a lost answer finds the document, never makes two
  const photoIds = new Map<File, string>()

  const dirty = computed(() => JSON.stringify(values) !== initial.value || photos.value.length > 0)
  const submitLabel = computed(() => {
    if (modelSaved.value) {
      return 'Try the photos again'
    }
    return props.model ? 'Save' : 'Add model'
  })
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
    duplicate.value = false
    photos.value = []
    photoStates.value = {}
    modelSaved.value = null
    photoIds.clear()
  }, { immediate: true })

  watch(() => [values.manufacturer, values.model], () => {
    duplicate.value = false
  })

  function onToggle (isOpen: boolean): void {
    if (!isOpen) {
      requestClose()
    }
  }

  function reload (): void {
    emit('reload')
    open.value = false
  }

  /** Send each photo and file it against the model; true when every one is in. */
  async function addPhotos (modelId: string): Promise<boolean> {
    let allIn = true
    for (const file of photos.value) {
      photoStates.value = { ...photoStates.value, [file.name]: 'Sending…' }
      const upload = uploads.add(file, { ownerRef: `document:model:${modelId}`, kind: 'document' })
      try {
        if (!(await upload.start())) {
          throw new Error(upload.error ?? 'The upload did not finish.')
        }
        let id = photoIds.get(file)
        if (!id) {
          id = newId()
          photoIds.set(file, id)
        }
        await documentsApi.create({
          id,
          scope: 'model',
          scope_id: modelId,
          doc_type: PHOTO_TYPE,
          title: titleFromFilename(file.name),
          language: 'en',
          client_visible: false,
          media_id: upload.mediaId!,
        })
        photos.value = photos.value.filter(f => f !== file)
        photoStates.value = { ...photoStates.value, [file.name]: 'Added' }
      } catch (error) {
        allIn = false
        photoStates.value = {
          ...photoStates.value,
          [file.name]: error instanceof NetworkError
            ? 'Not sent: no connection'
            : (error instanceof ApiError ? error.detail : (error as Error).message),
        }
      } finally {
        uploads.drop(upload)
      }
    }
    emit('photos', modelId)
    return allIn
  }

  async function save (): Promise<void> {
    message.value = null
    errors.value = validateModel(values)
    if (Object.keys(errors.value).length > 0) {
      await focusFirstError()
      return
    }
    const patch = props.model && !modelSaved.value ? modelPatchBody(values, props.model) : null
    if (props.model && !patch && photos.value.length === 0) {
      open.value = false
      return
    }
    busy.value = true
    try {
      if (!modelSaved.value) {
        const saved = props.model
          ? (patch ? await sensorModelsApi.update(props.model.id, patch) : props.model)
          : await sensorModelsApi.create(modelCreateBody(values))
        modelSaved.value = saved
        initial.value = JSON.stringify(values)
        emit('saved', saved)
      }
      if (photos.value.length > 0 && !(await addPhotos(modelSaved.value.id))) {
        const left = photos.value.length
        message.value = `The model is saved. ${left === 1 ? '1 photo was' : `${left} photos were`} not added: see below, then try again. You can also add photos from the model’s page.`
        return
      }
      open.value = false
    } catch (error) {
      if (error instanceof NetworkError) {
        message.value = 'We couldn’t reach the server. What you typed is still here: try again when you have signal.'
      } else if (error instanceof ApiError) {
        const problem = modelProblem(error, values)
        if (problem.kind === 'stale') {
          stale.value = true
        } else if (problem.kind === 'fields') {
          errors.value = problem.errors
          duplicate.value = error.code === 'model_taken'
          message.value = duplicate.value ? null : problem.message
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
