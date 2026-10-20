<template>
  <div ref="root" class="relative overflow-hidden bg-surface-100">
    <img
      v-if="url && !failed"
      :alt="alt"
      class="size-full"
      :class="fit === 'cover' ? 'object-cover' : 'object-contain'"
      decoding="async"
      :src="url"
      @error="failed = true"
    >

    <span v-else class="flex size-full items-center justify-center text-surface-500">
      <v-icon :icon="icon ?? icons.photo" :size="iconSize" />
    </span>
  </div>
</template>

<script lang="ts" setup>
  import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { documentsApi } from '@/api/operations'
  import { icons } from '@/app/theme/icons'
  import { photoUrl } from './photoLinks'

  // One photo of a sensor model, from a ten-minute link asked for once the picture is near the
  // screen (the list can hold dozens). With no photo, or when it can't be loaded (offline, the link
  // ran out), the icon stays: a missing picture is never an error on the page.
  const props = withDefaults(defineProps<{
    documentId: string | null
    alt?: string
    icon?: string
    iconSize?: number
    fit?: 'cover' | 'contain'
  }>(), { alt: '', icon: undefined, iconSize: 22, fit: 'cover' })

  const root = ref<HTMLElement | null>(null)
  const url = ref<string | null>(null)
  const failed = ref(false)
  const near = ref(typeof IntersectionObserver === 'undefined')
  let watcher: IntersectionObserver | undefined

  async function load (): Promise<void> {
    const id = props.documentId
    url.value = null
    failed.value = false
    if (!id || !near.value) {
      return
    }
    try {
      const link = await photoUrl(id, doc => documentsApi.download(doc, true))
      if (id === props.documentId) {
        url.value = link
      }
    } catch {
      failed.value = true
    }
  }

  onMounted(() => {
    if (typeof IntersectionObserver !== 'undefined' && root.value) {
      watcher = new IntersectionObserver(entries => {
        if (entries.some(e => e.isIntersecting)) {
          near.value = true
          watcher?.disconnect()
        }
      }, { rootMargin: '200px' })
      watcher.observe(root.value)
    }
  })
  onBeforeUnmount(() => watcher?.disconnect())

  watch([() => props.documentId, near], load, { immediate: true })
</script>
