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

    <v-list :aria-label="`Actions for ${doc.title}`" density="compact" role="menu">
      <v-list-item :prepend-icon="mdiPencilOutline" role="menuitem" title="Edit details" @click="emit('edit')" />
      <v-list-item :prepend-icon="icons.upload" role="menuitem" title="Upload a new version" @click="emit('new-version')" />

      <v-list-item
        v-if="doc.client_visible"
        :prepend-icon="mdiLockOutline"
        role="menuitem"
        title="Make staff only"
        @click="emit('visibility', false)"
      />

      <v-list-item
        v-else
        :prepend-icon="mdiEyeOutline"
        role="menuitem"
        :title="`Show to ${orgName ?? 'the owner organization'}`"
        @click="emit('visibility', true)"
      />
    </v-list>
  </v-menu>
</template>

<script lang="ts" setup>
  import type { DocumentOut } from '@/api/models'
  import { mdiDotsVertical, mdiEyeOutline, mdiLockOutline, mdiPencilOutline } from '@mdi/js'
  import { icons } from '@/app/theme/icons'

  // The row's actions for technicians and admins (DOC-3, DOC-4): details, a new version, who sees it
  defineProps<{
    doc: Pick<DocumentOut, 'title' | 'client_visible'>
    orgName?: string | null
  }>()

  const emit = defineEmits<{
    'edit': []
    'new-version': []
    'visibility': [visible: boolean]
  }>()
</script>
