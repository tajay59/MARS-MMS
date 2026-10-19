<template>
  <!-- A dialog from 768 px; a sheet rising from the bottom on phones (W6 screens) -->
  <v-dialog
    v-if="mdAndUp"
    v-model="open"
    :max-width="maxWidth"
    :persistent="persistent"
    scrollable
  >
    <div :aria-labelledby="labelledby" class="flex max-h-[calc(100dvh-48px)] flex-col overflow-y-auto overscroll-contain rounded-card bg-surface p-6" role="dialog">
      <slot />
    </div>
  </v-dialog>

  <v-bottom-sheet
    v-else
    v-model="open"
    :persistent="persistent"
  >
    <div
      :aria-labelledby="labelledby"
      class="flex max-h-[85dvh] flex-col overflow-y-auto overscroll-contain rounded-t-card bg-surface px-5 pt-5 pb-[calc(20px+env(safe-area-inset-bottom))]"
      role="dialog"
    >
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
