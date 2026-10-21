<template>
  <!-- An admin: one button to take the request, and a chevron that opens the staff picker -->
  <v-btn-group
    v-if="canAssign"
    :class="compact ? 'h-5!' : ''"
    color="primary"
    density="default"
    divided
    rounded="lg"
    variant="flat"
  >
    <v-btn
      :aria-label="`Claim ${requestRef}`"
      class="rounded-e-none! border-on-primary/40 font-semibold"
      :class="compact ? 'px-2! text-xs!' : ''"
      :height="height"
      :loading="loading"
      :prepend-icon="mdiCheckCircleOutline"
      @click="emit('claim')"
    >Claim</v-btn>

    <v-btn
      aria-haspopup="dialog"
      :aria-label="`Assign ${requestRef} to staff`"
      class="rounded-s-none! px-2"
      :height="height"
      :icon="mdiChevronDown"
      :size="compact ? 'x-small' : undefined"
      @click="emit('assign')"
    />
  </v-btn-group>

  <!-- A technician can only take it themselves -->
  <v-btn
    v-else
    :aria-label="`Claim ${requestRef}`"
    class="font-semibold"
    :class="compact ? 'px-2! text-xs!' : ''"
    color="primary"
    :height="height"
    :loading="loading"
    :prepend-icon="mdiCheckCircleOutline"
    rounded="lg"
    @click="emit('claim')"
  >Claim</v-btn>
</template>

<script lang="ts" setup>
  import { mdiCheckCircleOutline, mdiChevronDown } from '@mdi/js'
  import { computed } from 'vue'

  // The queue's action for one request (PRD REQ-7, AFD J4 step 4b and J5): a split button.
  // The main part claims; for an admin the chevron opens the Assign staff dialog.
  // `compact` is half the usual height (20 px): for a table row with a mouse, not for a thumb.
  const props = defineProps<{
    requestRef: string
    canAssign: boolean
    loading?: boolean
    compact?: boolean
  }>()

  const height = computed(() => props.compact ? 20 : undefined)

  const emit = defineEmits<{ claim: [], assign: [] }>()
</script>
