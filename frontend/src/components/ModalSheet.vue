<template>
  <!-- A dialog from 768 px; a sheet rising from the bottom on phones (W6 screens). `sheet` keeps the sheet on wide screens too, centred and as wide as `maxWidth` -->
  <v-dialog
    v-if="mdAndUp && !sheet"
    v-model="open"
    :aria-labelledby="labelledby"
    :max-width="maxWidth"
    :persistent="persistent"
    scrollable
  >
    <div class="flex max-h-[calc(100dvh-48px)] flex-col overflow-y-auto overscroll-contain rounded-card bg-surface p-6">
      <slot />
    </div>
  </v-dialog>

  <v-bottom-sheet
    v-else
    v-model="open"
    :aria-labelledby="labelledby"
    :inset="mdAndUp"
    :max-width="mdAndUp ? maxWidth : undefined"
    :persistent="persistent"
  >
    <div class="flex max-h-[85dvh] flex-col overflow-y-auto overscroll-contain rounded-t-card bg-surface px-5 pt-5 pb-[calc(20px+env(safe-area-inset-bottom))]">
      <slot />
    </div>
  </v-bottom-sheet>
</template>

<script lang="ts" setup>
  import { nextTick, watch } from 'vue'
  import { useDisplay } from 'vuetify'

  // The shell of the upload, new-version and form dialogs: the content brings its own heading,
  // whose id is `labelledby`. `persistent` keeps a click outside from closing it while a file is
  // going up or a form has unsaved changes.
  defineProps<{
    labelledby: string
    maxWidth?: number | string
    persistent?: boolean
    sheet?: boolean
  }>()

  const open = defineModel<boolean>({ required: true })
  const { mdAndUp } = useDisplay()

  // Focus goes back to what opened the dialog (WCAG 2.4.3): Vuetify does that only for an activator
  let opener: HTMLElement | null = null
  watch(open, async isOpen => {
    if (isOpen) {
      opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    } else {
      await nextTick()
      if (opener?.isConnected) {
        opener.focus({ preventScroll: true })
      }
      opener = null
    }
  })
</script>
