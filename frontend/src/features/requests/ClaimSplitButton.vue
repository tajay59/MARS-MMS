<template>
  <!-- An admin: one button to take the request, and a chevron that opens the staff picker -->
  <v-btn-group
    v-if="canAssign"
    color="primary"
    density="default"
    divided
    rounded="lg"
    variant="flat"
  >
    <v-btn
      :aria-label="`Claim ${requestRef}`"
      class="rounded-e-none! border-on-primary/40 font-semibold"
      :loading="loading"
      :prepend-icon="mdiCheckCircleOutline"
      @click="emit('claim')"
    >Claim</v-btn>

    <v-btn
      aria-haspopup="dialog"
      :aria-label="`Assign ${requestRef} to staff`"
      class="rounded-s-none! px-2"
      :icon="mdiChevronDown"
      @click="emit('assign')"
    />
  </v-btn-group>

  <!-- A technician can only take it themselves -->
  <v-btn
    v-else
    :aria-label="`Claim ${requestRef}`"
    class="font-semibold"
    color="primary"
    :loading="loading"
    :prepend-icon="mdiCheckCircleOutline"
    rounded="lg"
    @click="emit('claim')"
  >Claim</v-btn>
</template>

<script lang="ts" setup>
  import { mdiCheckCircleOutline, mdiChevronDown } from '@mdi/js'

  // The queue's action for one request (PRD REQ-7, AFD J4 step 4b and J5): a split button.
  // The main part claims; for an admin the chevron opens the Assign staff dialog.
  defineProps<{
    requestRef: string
    canAssign: boolean
    loading?: boolean
  }>()

  const emit = defineEmits<{ claim: [], assign: [] }>()
</script>
