<template>
  <!-- An admin: one button to take the request, and a chevron that opens the staff picker -->
  <v-btn-group
    v-if="canAssign"
    class="h-10!"
    color="primary"
    density="default"
    divided
    rounded="lg"
    variant="flat"
  >
    <v-btn
      :aria-label="`Claim ${requestRef}`"
      class="rounded-e-none! border-on-primary/40 font-semibold"
      height="40"
      :loading="loading"
      :prepend-icon="mdiCheckCircleOutline"
      @click="emit('claim')"
    >Claim</v-btn>

    <v-btn
      aria-haspopup="dialog"
      :aria-label="`Assign ${requestRef} to staff`"
      class="rounded-s-none! px-2"
      height="40"
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
    height="40"
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
  // Both parts are 40 px high, the same as every other button (the button group itself would
  // otherwise be 48 px and stretch them)
  defineProps<{
    requestRef: string
    canAssign: boolean
    loading?: boolean
  }>()

  const emit = defineEmits<{ claim: [], assign: [] }>()
</script>
