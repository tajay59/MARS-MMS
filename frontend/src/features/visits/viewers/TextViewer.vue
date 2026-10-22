<template>
  <div class="min-h-0 flex-1 overflow-auto bg-surface-50">
    <div v-if="lines === null" aria-label="Opening the file…" class="p-4" role="status">
      <v-skeleton-loader type="paragraph" />
    </div>

    <pre
      v-else
      :aria-label="`${filename}, ${lines.length} ${lines.length === 1 ? 'line' : 'lines'}`"
      class="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 py-3 pr-4 font-mono text-[13px] leading-relaxed text-surface-900"
      tabindex="0"
      translate="no"
    ><template v-for="(line, i) in lines" :key="i"><span aria-hidden="true" class="select-none pl-4 text-right text-surface-500">{{ i + 1 }}</span><span class="whitespace-pre">{{ line || ' ' }}</span></template></pre>
  </div>
</template>

<script lang="ts" setup>
  import { ref, watch } from 'vue'
  import { decodeText, linesOf } from './view'

  // A text or code file, read as UTF-8 and shown as text with line numbers (W11-29). Vue escapes
  // every line, so nothing in the file is ever treated as HTML. A file that turns out not to be
  // text (a NUL byte, bad UTF-8) is handed back to be shown as a file to download.
  const props = defineProps<{ url: string, filename: string }>()
  const emit = defineEmits<{ unreadable: [reason: 'binary' | 'offline' | 'failed'] }>()

  const lines = ref<string[] | null>(null)

  async function read (): Promise<void> {
    lines.value = null
    try {
      const response = await fetch(props.url, { credentials: 'omit', cache: 'no-store' })
      if (!response.ok) {
        emit('unreadable', 'failed')
        return
      }
      const text = decodeText(await response.arrayBuffer())
      if (text === null) {
        emit('unreadable', 'binary')
        return
      }
      lines.value = linesOf(text)
    } catch {
      emit('unreadable', navigator.onLine ? 'failed' : 'offline')
    }
  }

  watch(() => props.url, read, { immediate: true })
</script>
