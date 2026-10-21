<template>
  <div class="flex max-w-4xl flex-col gap-6">
    <div class="grid gap-x-5 gap-y-4 md:grid-cols-2">
      <FormField id="tpl-name" label="Name">
        <v-text-field
          id="tpl-name"
          v-model="draft.name"
          autocomplete="off"
          class="[&_.v-field]:bg-surface-50"
          flat
          hide-details="auto"
          :maxlength="MAX_NAME"
          name="name"
          :readonly="readonly"
          variant="solo-inverted"
        />
      </FormField>

      <!-- Fixed once a template exists: a new one chooses what it is for -->
      <div v-if="creating" class="flex flex-col gap-2">
        <span id="tpl-for-h" class="text-label text-surface-900">Applies to</span>

        <v-radio-group
          v-model="scope.kind"
          aria-labelledby="tpl-for-h"
          density="comfortable"
          hide-details
          inline
        >
          <v-radio label="A station type" value="type" />
          <v-radio label="A sensor model" value="model" />
        </v-radio-group>

        <v-text-field
          v-if="scope.kind === 'type'"
          v-model="scope.type"
          aria-label="Station type"
          autocomplete="off"
          class="[&_.v-field]:bg-surface-50"
          flat
          hide-details="auto"
          list="tpl-types"
          :maxlength="60"
          placeholder="For example AWS"
          variant="solo-inverted"
        />

        <v-select
          v-else
          v-model="scope.modelId"
          aria-label="Sensor model"
          class="[&_.v-field]:bg-surface-50"
          flat
          hide-details="auto"
          item-title="title"
          item-value="value"
          :items="models"
          placeholder="Choose a model"
          variant="solo-inverted"
        />

        <datalist id="tpl-types">
          <option v-for="type in types" :key="type" :value="type" />
        </datalist>

        <p class="m-0 text-sm text-surface-600">
          {{ scope.kind === 'type'
            ? 'Given to visits at stations of this type, written as on the stations. Capitals do not matter.'
            : 'Added to the list of every station that has one of these installed.' }}
          It can’t be changed once it is saved.
        </p>
      </div>

      <div v-else class="flex flex-col gap-2">
        <span class="text-label text-surface-900">Applies to</span>

        <div class="flex h-10 items-center gap-2.5 rounded-md px-3 text-surface-700 ring-1 ring-surface-300 ring-inset">
          <v-icon :icon="mdiLockOutline" size="18" />
          <span>{{ appliesText }}</span>
        </div>

        <p class="m-0 text-sm text-surface-600">Fixed once it is created.</p>
      </div>

      <div class="flex items-start gap-3 md:col-span-2">
        <v-switch
          v-model="draft.active"
          aria-label="Active"
          class="shrink-0"
          color="primary"
          density="compact"
          hide-details
          :readonly="readonly"
        />

        <div class="flex flex-col">
          <span class="font-semibold text-surface-900">Active</span>
          <span class="text-sm text-surface-600">Given to new visits that match. Turn it off to stop using it; nothing is deleted.</span>
        </div>
      </div>
    </div>

    <section aria-labelledby="tpl-items-h" class="flex flex-col gap-3">
      <div class="flex items-baseline justify-between gap-3">
        <h3 id="tpl-items-h" class="m-0 text-h3 text-surface-900">Items</h3>
        <span class="text-sm tabular-nums text-surface-600">{{ draft.items.length }} of {{ MAX_ITEMS }}</span>
      </div>

      <ol aria-labelledby="tpl-items-h" class="m-0 flex list-none flex-col gap-1.5 p-0">
        <li
          v-for="(item, index) in draft.items"
          :key="item.key"
          class="grid grid-cols-[auto_1.5rem_minmax(0,1fr)_auto] items-start gap-x-2 gap-y-1 rounded-lg py-1.5 transition-colors duration-200 md:grid-cols-[auto_1.5rem_minmax(0,1.3fr)_minmax(0,1fr)_auto] md:items-center"
          :class="[changed.has(item.key) && !readonly ? 'bg-primary-50' : '', overIndex === index && dragFrom !== null && dragFrom !== index ? 'outline-2 -outline-offset-2 outline-primary' : '']"
          :draggable="armed === index"
          @dragend="endDrag"
          @dragover.prevent="overIndex = index"
          @dragstart="startDrag($event, index)"
          @drop.prevent="dropOn(index)"
        >
          <button
            v-if="!readonly"
            :ref="el => grip(el, index)"
            :aria-label="`Item ${index + 1}. Press the up or down arrow to move it, or drag`"
            class="grid size-9 cursor-grab place-items-center rounded-md border-0 bg-transparent text-surface-600 hover:bg-surface-100 focus-visible:outline-2 focus-visible:outline-primary"
            type="button"
            @keydown.down.prevent="nudge(index, 1)"
            @keydown.up.prevent="nudge(index, -1)"
            @pointercancel="armed = null"
            @pointerdown="armed = index"
            @pointerup="armed = null"
          >
            <v-icon :icon="mdiDragVertical" size="20" />
          </button>

          <span v-else />

          <span aria-hidden="true" class="pt-2.5 text-right text-xs tabular-nums text-surface-600 md:pt-0">{{ index + 1 }}</span>

          <v-text-field
            :id="`tpl-item-${item.key}`"
            v-model="item.label"
            :aria-label="`Item ${index + 1}`"
            autocomplete="off"
            class="[&_.v-field]:bg-surface-50"
            density="compact"
            flat
            hide-details="auto"
            :maxlength="MAX_LABEL"
            :readonly="readonly"
            variant="solo-inverted"
          />

          <v-text-field
            v-model="item.help"
            :aria-label="`Help for item ${index + 1}`"
            autocomplete="off"
            class="col-start-3 md:col-start-auto [&_.v-field]:bg-surface-50"
            density="compact"
            flat
            hide-details="auto"
            :maxlength="MAX_HELP"
            placeholder="Add help for the technician"
            :readonly="readonly"
            variant="solo-inverted"
          />

          <v-btn
            v-if="!readonly"
            :aria-label="`Remove item ${index + 1}`"
            class="row-start-1 col-start-4 md:row-start-auto md:col-start-auto"
            icon
            size="36"
            variant="text"
            @click="remove(index)"
          >
            <v-icon :icon="mdiTrashCanOutline" size="20" />
          </v-btn>

          <span v-else />
        </li>
      </ol>

      <!-- Said aloud for a screen reader when an item is moved with the keyboard -->
      <p aria-live="polite" class="sr-only" role="status">{{ announce }}</p>

      <div v-if="!readonly" class="flex flex-wrap items-center gap-3">
        <v-btn
          class="text-primary"
          :disabled="draft.items.length >= MAX_ITEMS"
          :prepend-icon="mdiPlus"
          variant="outlined"
          @click="add"
        >Add item</v-btn>

        <span class="text-sm text-surface-600">Drag the handle to reorder, or press the up and down arrows on it.</span>
      </div>
    </section>

    <slot />
  </div>
</template>

<script lang="ts" setup>
  import type { Draft, Scope } from './checklists'
  import { mdiDragVertical, mdiLockOutline, mdiPlus, mdiTrashCanOutline } from '@mdi/js'
  import { nextTick, ref } from 'vue'
  import FormField from '@/components/FormField.vue'
  import { blankItem, MAX_HELP, MAX_ITEMS, MAX_LABEL, MAX_NAME, move } from './checklists'

  // The fields and the list of items of one template (PRD VIS-8; the "AWS-MMS W10 screens" boards).
  // The page owns the draft and what saving does; this only edits it. An older version or a viewer
  // with no right to change it is `readonly`.
  const draft = defineModel<Draft>({ required: true })

  defineProps<{
    readonly?: boolean
    creating?: boolean
    appliesText?: string
    changed: ReadonlySet<string>
    types: string[]
    models: { value: string, title: string }[]
  }>()

  /** What a new template is for (only used while `creating`). */
  const scope = defineModel<Scope>('scope', { required: true })

  const armed = ref<number | null>(null) // the row whose handle is held: only that row can be dragged
  const dragFrom = ref<number | null>(null)
  const overIndex = ref<number | null>(null)
  const announce = ref('')
  const grips = new Map<number, HTMLElement>()

  function grip (el: unknown, index: number): void {
    if (el instanceof HTMLElement) {
      grips.set(index, el)
    } else {
      grips.delete(index)
    }
  }

  function startDrag (event: DragEvent, index: number): void {
    dragFrom.value = index
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move'
      event.dataTransfer.setData('text/plain', String(index))
    }
  }

  function dropOn (index: number): void {
    if (dragFrom.value !== null) {
      draft.value.items = move(draft.value.items, dragFrom.value, index)
    }
    endDrag()
  }

  function endDrag (): void {
    dragFrom.value = null
    overIndex.value = null
    armed.value = null
  }

  async function nudge (index: number, by: number): Promise<void> {
    const to = index + by
    if (to < 0 || to >= draft.value.items.length) {
      return
    }
    draft.value.items = move(draft.value.items, index, to)
    announce.value = `Item moved to position ${to + 1} of ${draft.value.items.length}`
    await nextTick()
    grips.get(to)?.focus()
  }

  async function add (): Promise<void> {
    const item = blankItem()
    draft.value.items.push(item)
    await nextTick()
    document.querySelector<HTMLInputElement>(`#tpl-item-${item.key}`)?.focus()
  }

  function remove (index: number): void {
    draft.value.items.splice(index, 1)
    announce.value = `Item ${index + 1} removed`
  }
</script>
