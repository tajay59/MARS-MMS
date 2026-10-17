<template>
  <span :aria-label="APP_NAME" class="inline-flex shrink-0 items-center" :class="wordmark ? 'gap-3' : ''" role="img">
    <img
      alt=""
      class="shrink-0"
      :height="size"
      :src="logo.mark"
      :width="size"
    >

    <img
      v-if="wordmark"
      alt=""
      :height="wordHeight"
      :src="white ? logo.wordmarkWhite : logo.wordmark"
      :width="Math.round(wordHeight * WORDMARK_RATIO)"
    >
  </span>
</template>

<script lang="ts" setup>
  import { computed } from 'vue'
  import { useTheme } from 'vuetify'
  import { APP_NAME, logo } from '@/app/brand'

  // The MARS-MMS mark, with the wordmark beside it when there is room (DBD D1).
  const props = withDefaults(defineProps<{
    /** Height of the mark in px. */
    size?: number
    wordmark?: boolean
    /** The surface behind it: dark gets the white wordmark; auto follows the theme. */
    surface?: 'auto' | 'light' | 'dark'
  }>(), { size: 32, wordmark: true, surface: 'auto' })

  // Width ÷ height of the wordmark file, so its box is reserved before it loads (no layout shift)
  const WORDMARK_RATIO = 338 / 96

  const theme = useTheme()
  const wordHeight = computed(() => Math.round(props.size * 0.62))
  const white = computed(() => props.surface === 'dark' || (props.surface === 'auto' && theme.current.value.dark))
</script>
