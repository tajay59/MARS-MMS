<template>
  <!-- Vuetify puts role="dialog" on the overlay itself; an alert dialog says so there, not on a nested element -->
  <v-dialog
    v-model="open"
    aria-labelledby="dc-h"
    max-width="420"
    role="alertdialog"
  >
    <div class="flex flex-col gap-4 rounded-card bg-surface p-6">
      <h2 id="dc-h" class="m-0 text-h2 text-surface-900">Leave without saving?</h2>
      <p class="m-0 text-surface-700">{{ message }}</p>

      <div class="flex justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="open = false">Keep editing</v-btn>
        <v-btn color="error" @click="emit('leave')">Leave</v-btn>
      </div>
    </div>
  </v-dialog>
</template>

<script lang="ts" setup>
  // The question a dialog form asks before it throws away what was typed. Closing it with Escape
  // or a click outside means "keep editing".
  defineProps<{
    message: string
  }>()

  const open = defineModel<boolean>({ required: true })

  const emit = defineEmits<{
    leave: []
  }>()
</script>
