<template>
  <ModalSheet v-model="open" labelledby="su-h" max-width="420">
    <div class="flex flex-col gap-4">
      <div class="flex size-12 items-center justify-center rounded-full bg-warning-container text-warning">
        <v-icon :icon="mdiAlertOutline" size="26" />
      </div>

      <h2 id="su-h" class="m-0 text-h2 text-surface-900">This visit is not on your phone</h2>

      <p class="m-0 text-surface-900">
        If you lose signal at the station, you will not be able to record anything. Prepare it now while you have a connection.
      </p>

      <div class="flex flex-col gap-2.5">
        <v-btn block color="primary" :height="52" @click="emit('prepare')">Prepare now</v-btn>
        <v-btn block :height="48" variant="outlined" @click="emit('anyway')">Start anyway</v-btn>
      </div>
    </div>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import { mdiAlertOutline } from '@mdi/js'
  import ModalSheet from '@/components/ModalSheet.vue'

  // Start visit when the visit is not prepared (OFF-9). Asked only with signal; "Start anyway" works
  // from the server as today, and the visit page keeps a standing note about it.
  const open = defineModel<boolean>({ required: true })
  const emit = defineEmits<{ prepare: [], anyway: [] }>()
</script>
