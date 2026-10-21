<template>
  <!-- One main action (Approve, for an admin on a new request); the rest are outlined (DBD "Request page") -->
  <v-btn
    v-if="can(detail, 'approve')"
    :block="full"
    color="primary"
    :loading="busy === 'approve'"
    :prepend-icon="mdiCheck"
    @click="emit('approve')"
  >Approve</v-btn>

  <v-btn
    v-if="can(detail, 'schedule_visit')"
    :block="full"
    color="primary"
    :prepend-icon="mdiPlus"
    @click="emit('schedule')"
  >Schedule visit</v-btn>

  <v-btn
    v-if="can(detail, 'assign')"
    :block="full"
    color="primary"
    :prepend-icon="mdiAccountPlusOutline"
    @click="emit('assign')"
  >{{ detail.status === 'assigned' ? 'Change staff' : 'Assign staff' }}</v-btn>

  <v-btn
    v-if="can(detail, 'claim')"
    :block="full"
    color="primary"
    :loading="busy === 'claim'"
    :variant="can(detail, 'assign') ? 'outlined' : 'flat'"
    @click="emit('claim')"
  >Claim</v-btn>

  <v-btn
    v-if="can(detail, 'release')"
    :block="full"
    color="primary"
    :loading="busy === 'release'"
    variant="outlined"
    @click="emit('release')"
  >{{ isAdmin ? 'Unassign' : 'Release to queue' }}</v-btn>

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
  import { mdiAccountPlusOutline, mdiCheck, mdiPencilOutline, mdiPlus } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { useRoute } from 'vue-router'
  import { useSessionStore } from '@/stores/session'
  import { can } from './requests'

  // The buttons the server says this person may use on this request (`detail.actions`): the others
  // are not shown at all. A viewer's list is empty. `full` makes them as wide as the screen (phones).
  defineProps<{
    detail: RequestDetail
    busy?: 'approve' | 'claim' | 'release' | null
    full?: boolean
  }>()

  const emit = defineEmits<{ approve: [], deny: [], cancel: [], assign: [], claim: [], release: [], schedule: [] }>()
  const route = useRoute()
  const { isAdmin } = storeToRefs(useSessionStore())
</script>
