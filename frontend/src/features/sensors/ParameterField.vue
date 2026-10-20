<template>
  <div class="flex flex-col gap-2">
    <label :id="`${id}-label`" class="text-label text-surface-900" :for="id">Parameters it measures <span class="font-normal text-surface-600">(optional)</span></label>

    <ul v-if="codes.length > 0" :aria-labelledby="`${id}-label`" class="m-0 flex list-none flex-wrap gap-1.5 p-0">
      <li v-for="code in codes" :key="code">
        <v-chip closable :close-label="`Remove ${code}`" size="small" @click:close="remove(code)">
          <span class="font-mono" translate="no">{{ code }}</span>
        </v-chip>
      </li>
    </ul>

    <v-text-field
      :id="id"
      v-model="typed"
      autocomplete="off"
      class="[&_input]:font-mono"
      :error-messages="error"
      hint="Press Enter to add. Codes are capitals, numbers and _, such as AT or SOIL_T."
      name="parameter"
      persistent-hint
      placeholder="AT"
      spellcheck="false"
      @blur="addTyped"
      @keydown.enter.prevent="addTyped"
    />

    <div v-if="suggested.length > 0" aria-label="Parameters other models measure" class="flex flex-wrap gap-1.5" role="group">
      <button
        v-for="code in suggested"
        :key="code"
        class="inline-flex h-7 items-center rounded-full border border-dashed border-surface-500 px-2.5 font-mono text-sm text-surface-700 hover:bg-surface-100"
        translate="no"
        type="button"
        @click="add(code)"
      >+ {{ code }}</button>
    </div>
  </div>
</template>

<script lang="ts" setup>
  import { computed, ref } from 'vue'
  import { normalizeParameter } from './sensorForms'

  // Parameter codes as chips, typed or picked from what other models measure. The same rules as
  // the station form's (capitals, numbers and _), kept short by the model's limit.
  const props = defineProps<{
    id: string
    error?: string
    /** Codes other models and stations already use, offered as picks. */
    suggestions: string[]
  }>()

  const codes = defineModel<string[]>({ required: true })
  const typed = ref('')

  const suggested = computed(() => {
    const have = new Set(codes.value)
    return props.suggestions.filter(code => !have.has(code)).slice(0, 8)
  })

  /** The codes with `raws` added: each normalized, none twice. */
  function withCodes (raws: readonly string[]): string[] {
    const next = [...codes.value]
    for (const raw of raws) {
      const code = normalizeParameter(raw)
      if (code && !next.includes(code)) {
        next.push(code)
      }
    }
    return next
  }

  function add (raw: string): void {
    codes.value = withCodes([raw])
  }

  function addTyped (): void {
    // Commas and spaces separate codes, so a pasted list works. All are added in one go: the
    // model value only catches up on the next render, so adding them one by one lost all but the last
    codes.value = withCodes(typed.value.split(/[\s,;]+/))
    typed.value = ''
  }

  function remove (code: string): void {
    codes.value = codes.value.filter(c => c !== code)
  }
</script>
