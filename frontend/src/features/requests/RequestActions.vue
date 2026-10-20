<template>
  <!-- One main action (Approve, for an admin on a new request); the rest are outlined (DBD "Request page") -->
  <v-btn
    v-if="can(detail, 'approve')"
    :block="full"
    color="primary"
    :loading="busy"
    :prepend-icon="mdiCheck"
    @click="emit('approve')"
  >Approve</v-btn>

  <v-btn
    v-if="can(detail, 'deny')"
    :block="full"
    color="primary"
    variant="outlined"
    @click="emit('deny')"
  >Deny</v-btn>

  <v-btn
    v-if="can(detail, 'edit')"
    :block="full"
    color="primary"
    :prepend-icon="mdiPencilOutline"
    :to="{ name: 'requests', params: { id: detail.id, mode: 'edit' }, query: route.query }"
    variant="outlined"
  >Edit</v-btn>

  <v-btn
    v-if="can(detail, 'cancel')"
    :block="full"
    color="primary"
    variant="outlined"
    @click="emit('cancel')"
  >Cancel request</v-btn>
</template>

<script lang="ts" setup>
  import type { RequestDetail } from '@/api/models'
  import { mdiCheck, mdiPencilOutline } from '@mdi/js'
  import { useRoute } from 'vue-router'
  import { can } from './requests'

  // The buttons the server says this person may use on this request (`detail.actions`): the others
  // are not shown at all. A viewer's list is empty. `full` makes them as wide as the screen (phones).
  defineProps<{
    detail: RequestDetail
    busy?: boolean
    full?: boolean
  }>()

  const emit = defineEmits<{ approve: [], deny: [], cancel: [] }>()
  const route = useRoute()
</script>
