<template>
  <v-menu location="bottom end">
    <template #activator="{ props: activator }">
      <v-btn
        v-bind="activator"
        :aria-label="`More for ${unit.serial}`"
        icon
        size="40"
        variant="text"
      >
        <v-icon class="text-surface-700" :icon="mdiDotsVertical" size="20" />
      </v-btn>
    </template>

    <v-list :aria-label="`Actions for ${unit.serial}`" density="compact" role="menu">
      <v-list-item :prepend-icon="mdiPencilOutline" role="menuitem" title="Edit unit" @click="$emit('edit')" />
    </v-list>
  </v-menu>
</template>

<script lang="ts" setup>
  import type { SensorUnitOut } from '@/api/models'
  import { mdiDotsVertical, mdiPencilOutline } from '@mdi/js'

  // The actions on one unit (for those who may write).
  defineProps<{
    unit: Pick<SensorUnitOut, 'serial'>
  }>()

  defineEmits<{
    edit: []
  }>()
</script>
