<template>
  <ModalSheet
    labelledby="dd-h"
    :max-width="480"
    :model-value="open"
    persistent
    @update:model-value="onToggle"
  >
    <form class="flex flex-col gap-4" novalidate @submit.prevent="save">
      <div>
        <h2 id="dd-h" class="m-0 text-h2 text-surface-900">Edit details</h2>

        <p v-if="doc" class="m-0 mt-0.5 break-words text-sm text-surface-600">
          <span translate="no">{{ doc.filename }}</span> · {{ formatBytes(doc.size_bytes) }}
        </p>
      </div>

      <FeedbackBanner v-if="stale" type="warning">
        <div class="font-semibold">Someone else changed this document.</div>
        <div>Reload to see their changes, then make yours again.</div>
      </FeedbackBanner>

      <FeedbackBanner v-else-if="message" type="error">{{ message }}</FeedbackBanner>

      <FormField id="dd-title" label="Title">
        <v-text-field
          id="dd-title"
          v-model="values.title"
          autocomplete="off"
          :error-messages="errors.title"
          maxlength="120"
          name="title"
        />
      </FormField>

      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FormField id="dd-type" label="Type">
          <v-select
            id="dd-type"
            v-model="values.docType"
            :error-messages="errors.docType"
            item-title="label"
            item-value="value"
            :items="types"
            name="doc_type"
          />
        </FormField>

        <FormField id="dd-version" label="Version label (optional)">
          <v-text-field
            id="dd-version"
            v-model="values.versionLabel"
            autocomplete="off"
            :error-messages="errors.versionLabel"
            maxlength="60"
            name="version_label"
            placeholder="v1, Rev C…"
          />
        </FormField>
      </div>

      <FormField id="dd-language" label="Language">
        <v-select
          id="dd-language"
          v-model="values.language"
          clearable
          :error-messages="errors.language"
          item-title="label"
          item-value="value"
          :items="languages"
          name="language"
        />
      </FormField>

      <FormField id="dd-description" label="Description (optional)">
        <v-textarea
          id="dd-description"
          v-model="values.description"
          auto-grow
          autocomplete="off"
          :error-messages="errors.description"
          maxlength="2000"
          name="description"
          rows="3"
        />
      </FormField>

      <p class="m-0 text-xs text-surface-600">To replace the file, use “Upload a new version”.</p>

      <div class="mt-1 flex justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="requestClose">Cancel</v-btn>

        <v-btn v-if="stale" color="primary" variant="outlined" @click="reload">Reload</v-btn>

        <v-btn
          v-else
          color="primary"
          :disabled="!dirty"
          :loading="busy"
          type="submit"
        >Save</v-btn>
      </div>
    </form>
  </ModalSheet>

  <DiscardConfirm v-model="askLeave" message="Your changes to this document’s details will be lost." @leave="leave" />
</template>

<script lang="ts" setup>
  import type { DetailErrors, DetailValues } from './documentDetails'
  import type { DocScope } from './documents'
  import type { DocumentOut } from '@/api/models'
  import { computed, reactive, ref, watch } from 'vue'
  import { documentsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { focusFirstError } from '@/app/composables/focusFirstError'
  import { useFormDialog } from '@/app/composables/useFormDialog'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { detailsPatchBody, detailsProblem, detailValues, sameDetails, validateDetails } from './documentDetails'
  import { docTypes, formatBytes, languages } from './documents'

  // Change a document's title, type, version label, language or description (PRD DOC-4). The file
  // never changes here, and who may see it stays in the row's menu. Online only (OFF-10).
  const props = defineProps<{
    /** The document being edited. */
    doc: DocumentOut | null
  }>()

  const emit = defineEmits<{
    saved: [doc: DocumentOut]
    reload: []
  }>()

  const open = defineModel<boolean>({ required: true })

  const values = reactive<DetailValues>({ title: '', docType: '', versionLabel: '', language: null, description: '' })
  const errors = ref<DetailErrors>({})
  const message = ref<string | null>(null)
  const stale = ref(false)
  const busy = ref(false)
  const initial = ref(JSON.stringify(values))

  const dirty = computed(() => JSON.stringify(values) !== initial.value)
  const types = computed(() => docTypes[(props.doc?.scope as DocScope | undefined) ?? 'station'])
  const { askLeave, requestClose, leave } = useFormDialog(open, () => dirty.value)

  watch(open, isOpen => {
    if (!isOpen || !props.doc) {
      return
    }
    Object.assign(values, detailValues(props.doc))
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

  /**
   * Send the change. A conflict is someone else's edit only when the details differ from what was
   * opened: media's checks also move the version, and then the same change goes again.
   */
  async function send (doc: DocumentOut): Promise<DocumentOut> {
    const patch = detailsPatchBody(values, doc)
    if (!patch) {
      return doc
    }
    try {
      return await documentsApi.update(doc.id, patch)
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 409) {
        throw error
      }
      const fresh = await documentsApi.get(doc.id)
      const again = sameDetails(fresh, doc) ? detailsPatchBody(values, fresh) : null
      if (!again) {
        throw error
      }
      return documentsApi.update(fresh.id, again)
    }
  }

  async function save (): Promise<void> {
    if (!props.doc) {
      return
    }
    message.value = null
    errors.value = validateDetails(values)
    if (Object.keys(errors.value).length > 0) {
      await focusFirstError()
      return
    }
    if (!detailsPatchBody(values, props.doc)) {
      open.value = false
      return
    }
    busy.value = true
    try {
      emit('saved', await send(props.doc))
      open.value = false
    } catch (error) {
      if (error instanceof NetworkError) {
        message.value = 'This needs a connection. It will save when you have signal.'
      } else if (error instanceof ApiError) {
        const problem = detailsProblem(error)
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
        message.value = 'We couldn’t save the details. Try again in a moment.'
      }
    } finally {
      busy.value = false
    }
  }
</script>
