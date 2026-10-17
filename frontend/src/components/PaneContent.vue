<template>
  <Teleport v-if="pane?.target.value" :to="pane.target.value">
    <slot />
  </Teleport>
</template>

<script lang="ts" setup>
  import { onBeforeUnmount } from 'vue'
  import { usePane } from '@/app/shells/pane'

  // The page's list or controls, shown in the shell's interactive pane (DBD "The app shell").
  const pane = usePane()
  if (pane) {
    pane.blocks.value++
    onBeforeUnmount(() => {
      pane.blocks.value--
    })
  }
</script>
