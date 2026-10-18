<template>
  <ModalSheet
    labelledby="nc-h"
    :max-width="540"
    :model-value="open"
    persistent
    @update:model-value="onToggle"
  >
    <form class="flex flex-col gap-4" novalidate @submit.prevent="save">
      <div>
        <h2 id="nc-h" class="m-0 text-h2 text-surface-900">New configuration version</h2>

        <p class="m-0 mt-0.5 text-sm text-surface-600">
          {{ station.name }} · becomes <strong class="font-semibold text-surface-900">version {{ nextVersion }}</strong>
        </p>
      </div>

      <FeedbackBanner v-if="error" type="error">{{ error }}</FeedbackBanner>

      <ul v-if="items.length > 0" aria-label="Files in this version" class="m-0 flex list-none flex-col border-b border-surface-200 p-0">
        <li v-for="item in items" :key="item.key" class="flex min-h-14 items-center gap-3 border-t border-surface-200 py-1.5">
          <v-icon class="shrink-0" :class="item.problem ? 'text-error' : 'text-surface-600'" :icon="item.problem ? mdiAlertCircleOutline : fileIcon(item.name).icon" size="22" />

          <div class="min-w-0 grow">
            <div class="truncate font-mono text-[13px] text-surface-900" translate="no">{{ item.name }}</div>

            <div v-if="item.problem" class="text-xs text-error" role="alert">{{ item.problem }}</div>
            <div v-else-if="item.upload?.state === 'failed'" class="text-xs text-error" role="alert">{{ item.upload.error }}</div>

            <div
              v-else-if="item.upload && (item.upload.state === 'running' || item.upload.state === 'idle')"
              :aria-label="`Sending ${item.name}`"
              aria-valuemax="100"
              aria-valuemin="0"
              :aria-valuenow="pctOf(item)"
              class="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-200"
              role="progressbar"
            >
              <div class="h-full bg-primary" :style="{ width: `${pctOf(item)}%` }" />
            </div>

            <div v-else-if="item.upload && (item.upload.state === 'arrived' || item.upload.state === 'checking')" class="text-xs text-on-info-container">Checking file…</div>
            <div v-else class="text-xs text-surface-600">{{ formatBytes(item.size) }}<template v-if="item.upload?.state === 'ready'"> · ready</template></div>
          </div>

          <span v-if="item.upload && item.upload.state === 'running'" class="text-xs tabular-nums text-surface-600">{{ pctOf(item) }}%</span>

          <v-btn
            v-if="item.upload?.state === 'failed'"
            :aria-label="`Try ${item.name} again`"
            icon
            size="40"
            variant="text"
            @click="tryAgain(item)"
          >
            <v-icon :icon="mdiRefresh" size="20" />
          </v-btn>

          <v-btn
            :aria-label="removeLabel(item)"
            :disabled="saving"
            icon
            size="40"
            variant="text"
            @click="remove(item)"
          >
            <v-icon class="text-surface-700" :icon="mdiClose" size="20" />
          </v-btn>
        </li>
      </ul>

      <div>
        <v-btn
          color="primary"
          :disabled="saving || items.length >= MAX_FILES"
          :prepend-icon="mdiPlus"
          variant="outlined"
          @click="picker?.click()"
        >Add files</v-btn>

        <input
          ref="picker"
          aria-label="Choose files"
          class="sr-only"
          data-testid="config-files"
          multiple
          tabindex="-1"
          type="file"
          @change="onPick"
        >
      </div>

      <FormField id="nc-notes" label="What changed">
        <v-textarea
          id="nc-notes"
          v-model="notes"
          auto-grow
          maxlength="2000"
          name="notes"
          placeholder="For example: sampling every 10 s, new modem APN"
          rows="3"
        />
      </FormField>

      <div class="flex items-start gap-2.5 rounded-md bg-surface-50 px-3 py-2.5 text-sm text-surface-700">
        <v-icon class="mt-0.5 shrink-0" :icon="mdiInformationOutline" size="18" />
        <span>Once saved, a version can’t be changed or deleted. To fix a mistake, save a new version.</span>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3">
        <span class="text-sm text-surface-600" role="status">{{ waitingText }}</span>

        <div class="flex gap-2">
          <v-btn class="text-primary" variant="text" @click="cancel">Cancel</v-btn>
          <v-btn color="primary" :disabled="!canSave" :loading="saving" type="submit">Save version {{ nextVersion }}</v-btn>
        </div>
      </div>
    </form>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { ConfigVersionOut, StationDetail } from '@/api/models'
  import type { Upload } from '@/app/composables/useUpload'
  import { mdiAlertCircleOutline, mdiClose, mdiInformationOutline, mdiPlus, mdiRefresh } from '@mdi/js'
  import { computed, ref, watch } from 'vue'
  import { configVersionsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { useUploads } from '@/app/composables/useUpload'
  import { newId } from '@/app/ids'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { duplicateName } from './configs'
  import { fileIcon, fileProblem, formatBytes, percent } from './documents'

  // New configuration version (CFG-1, CFG-2): files go up one by one as they are added, and the
  // version can be saved once every one has passed media's checks. A version is written once.
  const props = defineProps<{
    station: StationDetail
    nextVersion: number
  }>()

  const open = defineModel<boolean>({ required: true })

  const emit = defineEmits<{
    saved: [version: ConfigVersionOut]
  }>()

  const MAX_FILES = 50 // the server's limit
  const AT_ONCE = 2 // hashing holds a whole file in memory: keep a phone's share small

  interface Item {
    key: string
    name: string
    size: number
    problem: string | null
    upload: Upload | null
  }

  const uploads = useUploads()
  const picker = ref<HTMLInputElement | null>(null)
  const items = ref<Item[]>([])
  const notes = ref('')
  const error = ref<string | null>(null)
  const saving = ref(false)
  // One ID per version made in this dialog: a retry after a lost answer finds it, never makes two
  let versionId = newId()

  const sending = computed(() => items.value.filter(i => i.upload && ['running', 'arrived', 'checking'].includes(i.upload.state)).length)
  const ready = computed(() => items.value.filter(i => i.upload?.state === 'ready'))
  const notReady = computed(() => items.value.filter(i => i.upload && i.upload.state !== 'ready'))
  const canSave = computed(() => ready.value.length > 0 && notReady.value.length === 0 && !saving.value)
  const waitingText = computed(() => {
    const n = notReady.value.length
    if (n === 0) {
      return ready.value.length > 0 ? `${ready.value.length} ${ready.value.length === 1 ? 'file' : 'files'} ready` : 'Add the files of this version'
    }
    return `Waiting for ${n} ${n === 1 ? 'file' : 'files'}`
  })

  function pctOf (item: Item): number {
    return item.upload ? percent(item.upload.sent, item.upload.total) : 0
  }

  function removeLabel (item: Item): string {
    const state = item.upload?.state
    if (item.problem) {
      return `Dismiss ${item.name}`
    }
    return state === 'running' ? `Cancel ${item.name}` : `Remove ${item.name}`
  }

  function reset (): void {
    items.value = []
    notes.value = ''
    error.value = null
    saving.value = false
    versionId = newId()
  }

  watch(open, isOpen => {
    if (isOpen) {
      reset()
    }
  }, { immediate: true })

  function onPick (event: Event): void {
    const input = event.target as HTMLInputElement
    add([...(input.files ?? [])])
    input.value = ''
  }

  function add (files: File[]): void {
    error.value = null
    for (const file of files) {
      const names = items.value.filter(i => !i.problem).map(i => i.name)
      let problem = fileProblem(file, 'config')
      if (!problem && duplicateName(names, file.name)) {
        problem = 'A file with this name is already in this version.'
      }
      if (!problem && items.value.length >= MAX_FILES) {
        problem = 'A version can hold 50 files.'
      }
      const item: Item = {
        key: newId(),
        name: file.name,
        size: file.size,
        problem,
        upload: problem ? null : uploads.add(file, { ownerRef: `config:${props.station.id}`, kind: 'config', untilChecked: true }),
      }
      items.value.push(item)
    }
    pump()
  }

  /** Start waiting files, a couple at a time. */
  function pump (): void {
    for (const item of items.value) {
      if (sending.value >= AT_ONCE) {
        return
      }
      const upload = item.upload
      if (upload?.state === 'idle') {
        void upload.start().then(pump)
      }
    }
  }

  function tryAgain (item: Item): void {
    item.upload?.reset()
    pump()
  }

  async function remove (item: Item): Promise<void> {
    items.value = items.value.filter(i => i.key !== item.key)
    if (item.upload) {
      // Stops it, and takes a file that already arrived off the server: it is in no version
      await item.upload.cancel(true)
      uploads.drop(item.upload)
    }
    pump()
  }

  async function save (): Promise<void> {
    if (!canSave.value) {
      return
    }
    saving.value = true
    error.value = null
    const files = ready.value.map(i => ({ media_id: i.upload!.mediaId! }))
    try {
      let saved: ConfigVersionOut | null = null
      for (let attempt = 0; saved === null; attempt++) {
        try {
          saved = await configVersionsApi.create(props.station.id, { id: versionId, files, notes: notes.value.trim() || null })
        } catch (error_) {
          // A file media has just finished with may not have reached operations yet: a moment later it has
          if (error_ instanceof ApiError && error_.reason === 'file_not_ready' && attempt < 4) {
            await new Promise(resolve => setTimeout(resolve, 1500))
            continue
          }
          throw error_
        }
      }
      emit('saved', saved)
      open.value = false
    } catch (error_) {
      error.value = error_ instanceof NetworkError
        ? 'The connection dropped before the version was saved. Try again: it won’t be saved twice.'
        : (error_ instanceof ApiError ? error_.detail : 'The version could not be saved. Try again.')
    } finally {
      saving.value = false
    }
  }

  async function cancel (): Promise<void> {
    if (saving.value) {
      return
    }
    const abandoned = items.value
    items.value = []
    open.value = false
    // Files that arrived are in no version: take them off the server
    await Promise.all(abandoned.map(async i => {
      if (i.upload) {
        await i.upload.cancel(true)
        uploads.drop(i.upload)
      }
    }))
  }

  function onToggle (open: boolean): void {
    if (!open) {
      void cancel()
    }
  }
</script>
