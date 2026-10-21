<template>
  <!-- One main action (Start or End); the rest are outlined (DBD "Request page"). The server says what this person may do -->
  <v-btn
    v-if="canDo(visit, 'reschedule')"
    :block="full"
    color="primary"
    variant="outlined"
    @click="emit('reschedule')"
  >Reschedule</v-btn>

  <v-btn
    v-if="canDo(visit, 'cancel')"
    :block="full"
    color="primary"
    variant="outlined"
    @click="emit('cancel')"
  >Cancel visit</v-btn>

  <v-btn
    v-if="canDo(visit, 'restore')"
    :block="full"
    color="primary"
    :loading="busy === 'restore'"
    variant="outlined"
    @click="emit('restore')"
  >Restore visit</v-btn>

  <v-btn
    v-if="canDo(visit, 'start')"
    :block="full"
    color="primary"
    :loading="busy === 'start'"
    :prepend-icon="mdiPlay"
    @click="emit('start')"
  >Start visit</v-btn>

  <v-btn
    v-if="canDo(visit, 'end')"
    :block="full"
    color="primary"
    @click="emit('end')"
  >End visit</v-btn>
</template>

<script lang="ts" setup>
  import type { VisitOut } from '@/api/models'
  import { mdiPlay } from '@mdi/js'
  import { canDo } from './visits'

  // The buttons the server says this person may use on this visit (`visit.actions`): the others are
  // not shown at all. A client's and a viewer's list is empty. `full` makes them as wide as the
  // screen (phones).
  defineProps<{
    visit: VisitOut
    busy?: string | null
    full?: boolean
  }>()

  const emit = defineEmits<{ reschedule: [], cancel: [], start: [], end: [], restore: [] }>()
</script>
