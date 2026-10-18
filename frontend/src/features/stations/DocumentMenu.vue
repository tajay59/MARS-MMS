<template>
  <v-menu location="bottom end">
    <template #activator="{ props: activator }">
      <v-btn
        v-bind="activator"
        :aria-label="`More for ${doc.title}`"
        icon
        size="40"
        variant="text"
      >
        <v-icon class="text-surface-700" :icon="mdiDotsVertical" size="20" />
      </v-btn>
    </template>

    <v-list density="compact">
      <v-list-item :prepend-icon="icons.upload" title="Upload a new version" @click="emit('new-version')" />

      <v-list-item
        v-if="doc.client_visible"
        :prepend-icon="mdiLockOutline"
        title="Make staff only"
        @click="emit('visibility', false)"
      />

      <v-list-item
        v-else
        :prepend-icon="mdiEyeOutline"
        :title="`Show to ${orgName ?? 'the owner organization'}`"
        @click="emit('visibility', true)"
      />
    </v-list>
  </v-menu>
</template>

<script lang="ts" setup>
  import type { DocumentOut } from '@/api/models'
  import { mdiDotsVertical, mdiEyeOutline, mdiLockOutline } from '@mdi/js'
  import { icons } from '@/app/theme/icons'

  // The row's actions for technicians and admins (DOC-3, DOC-4)
  defineProps<{
    doc: Pick<DocumentOut, 'title' | 'client_visible'>
    orgName?: string | null
  }>()

  const emit = defineEmits<{
    'new-version': []
    'visibility': [visible: boolean]
  }>()
</script>
