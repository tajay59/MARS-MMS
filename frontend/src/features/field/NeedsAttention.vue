<template>
  <section v-if="concerns.length > 0" aria-labelledby="attention-h" class="flex flex-col gap-3">
    <h2 id="attention-h" class="m-0 text-h3 text-surface-900">Needs attention</h2>

    <article
      v-for="item in concerns"
      :key="item.key"
      class="flex flex-col gap-2 rounded-card border-l-4 border-error bg-surface-50 p-3.5"
    >
      <div class="flex items-baseline justify-between gap-2">
        <span class="font-mono text-sm font-medium text-surface-900" translate="no">{{ item.ref }}<template v-if="item.station"> · {{ item.station.code }}</template></span>
        <span class="text-xs text-surface-600">{{ item.what }}</span>
      </div>

      <p class="m-0 text-surface-900">{{ item.text }}</p>

      <div class="flex flex-wrap gap-2">
        <v-btn v-if="item.canExport" size="small" variant="outlined" @click="show(item, 'export')">Export</v-btn>
        <v-btn v-if="item.canRetry" size="small" variant="outlined" @click="retry(item)">Try again</v-btn>
        <v-btn class="text-primary" size="small" variant="text" @click="show(item, 'confirm')">Done with this</v-btn>

        <v-btn
          v-if="item.element || item.current"
          class="text-primary"
          size="small"
          variant="text"
          @click="show(item, 'detail')"
        >Details</v-btn>
      </div>
    </article>

    <ConflictSheet v-if="chosen" v-model="sheet" :concern="chosen" :start="start" />
  </section>
</template>

<script lang="ts" setup>
  import type { Concern } from '@/features/visits/local/attention'
  import { ref, watch } from 'vue'
  import { retryStuck } from '@/features/visits/local/attention'
  import { syncNow } from '@/features/visits/local/syncApp'
  import ConflictSheet from './ConflictSheet.vue'

  // Needs attention (AFD §6): what the server did not take, with the wording of the table. Export
  // opens the full sheet; Done with this asks once more before the phone lets go.
  const props = defineProps<{ concerns: Concern[] }>()

  const sheet = ref(false)
  const chosen = ref<Concern | null>(null)
  const start = ref<'detail' | 'export' | 'confirm'>('detail')

  function show (item: Concern, how: 'detail' | 'export' | 'confirm'): void {
    chosen.value = item
    start.value = how
    sheet.value = true
  }

  // The sheet shows the newest state of the item it opened
  watch(() => props.concerns, list => {
    if (chosen.value) {
      chosen.value = list.find(c => c.key === chosen.value!.key) ?? null
      if (!chosen.value) {
        sheet.value = false
      }
    }
  })

  async function retry (item: Concern): Promise<void> {
    await retryStuck(item.ops[0]!.user_id, item.visit_id)
    void syncNow(true).catch(() => undefined)
  }
</script>
