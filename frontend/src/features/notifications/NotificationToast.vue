<template>
  <v-snackbar
    v-model="visible"
    location="bottom end"
    :timeout="7000"
  >
    <span class="flex items-center gap-2.5">
      <v-icon :icon="iconFor(shown?.type ?? '')" size="20" />
      <span class="min-w-0"><b class="font-semibold">{{ shown?.title }}</b> <span>{{ shown?.body }}</span></span>
    </span>

    <template #actions>
      <v-btn color="inverse-primary" variant="text" @click="open">Open</v-btn>
    </template>
  </v-snackbar>
</template>

<script lang="ts" setup>
  import { storeToRefs } from 'pinia'
  import { ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useNotificationsStore } from '@/stores/notifications'
  import { iconFor } from './notifications'

  // A notification that arrives while the app is open, said for a few seconds (PRD NOT-1). Not on
  // the notifications page, where the list itself changes.
  const store = useNotificationsStore()
  const { arrived } = storeToRefs(store)
  const route = useRoute()
  const router = useRouter()
  const visible = ref(false)
  const shown = ref(arrived.value)

  watch(arrived, item => {
    if (item && route.name !== 'notifications') {
      shown.value = item
      visible.value = true
    }
    store.dismissToast()
  })

  async function open (): Promise<void> {
    visible.value = false
    if (shown.value) {
      void store.markRead(shown.value.id)
      await router.push(shown.value.link)
    }
  }
</script>
