<template>
  <section aria-labelledby="fp-h" class="flex flex-col gap-3 rounded-card border border-surface-200 bg-surface p-4">
    <div class="flex flex-col gap-1">
      <h2 id="fp-h" class="m-0 text-h4 text-surface-900">From the board</h2>
      <p class="m-0 text-sm text-surface-700">Only shared elements are in the report. Change them on the board and the report updates.</p>
    </div>

    <ul v-if="facts.length > 0" class="m-0 flex list-none flex-col gap-2 p-0">
      <li
        v-for="fact in facts"
        :key="fact.id"
        class="grid grid-cols-[10px_1fr] gap-x-3 gap-y-1 rounded-md border border-surface-200 px-3 py-2 sm:grid-cols-[10px_1fr_auto]"
        :class="fact.printed ? 'bg-surface-50' : 'border-dashed bg-surface'"
      >
        <span aria-hidden="true" class="row-span-2 self-stretch sm:row-span-1" :class="[swatch[fact.kind], fact.printed ? '' : 'opacity-60']" />

        <div class="min-w-0">
          <strong class="font-medium text-surface-900" :class="fact.printed ? '' : 'opacity-80'">{{ fact.title }}</strong>

          <div class="text-sm text-surface-700">
            <span class="font-mono text-xs" translate="no">{{ fact.station }}</span>
            ·
            <span v-if="!fact.printed" class="mr-1 inline-flex items-center gap-1 rounded-full border border-surface-500 bg-surface-100 px-2 text-xs font-medium text-surface-800">
              <v-icon :icon="mdiEyeOffOutline" size="12" />Staff only
            </span>
            {{ fact.line }}
          </div>

          <p v-if="!fact.printed" class="m-0 text-xs text-surface-600">Not in the report. Share it on the board to include it.</p>
        </div>

        <v-btn
          v-if="visitId"
          class="col-start-2 justify-self-start sm:col-start-3"
          color="primary"
          size="small"
          :to="{ name: 'visits', params: { id: visitId } }"
          variant="text"
        >{{ fact.printed ? 'Fix on the board' : 'Open on the board' }}</v-btn>
      </li>
    </ul>

    <p v-else class="m-0 text-sm text-surface-700">Nothing was recorded on the board for this visit.</p>
  </section>
</template>

<script lang="ts" setup>
  import type { Fact } from './rules'
  import { mdiEyeOffOutline } from '@mdi/js'

  // The "From the board" list of the editor (W17, boards 4 and the W17 sheet): every element with
  // whether it prints. A staff-only one is marked with a word as well as an icon.
  defineProps<{
    facts: Fact[]
    visitId: string | null
  }>()

  // The sticky-note tints of the board (DBD)
  const swatch = {
    task: 'bg-sticky-task',
    note: 'bg-sticky-note',
    recommendation: 'bg-sticky-recommendation',
    config: 'bg-sticky-config',
  } as const
</script>
