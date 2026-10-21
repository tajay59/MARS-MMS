<template>
  <!-- No border and no rounded corners: the header band, a hover and the picked row do the work -->
  <div ref="box" class="max-h-[400px] overflow-y-auto">
    <table class="w-full border-collapse text-sm">
      <caption class="sr-only">{{ label }}: pick a row to filter the queue by it</caption>

      <thead>
        <tr class="text-left">
          <th class="sticky top-0 bg-surface-100 px-3 py-2 text-xs font-medium text-surface-700" scope="col">{{ label }}</th>
          <th class="sticky top-0 bg-surface-100 px-3 py-2 text-right text-xs font-medium text-surface-700" scope="col">Requests</th>
        </tr>
      </thead>

      <tbody>
        <tr
          v-for="row in rows"
          :key="row.value ?? 'any'"
          class="cursor-pointer hover:bg-surface-100"
          :class="selected === row.value ? 'bg-primary-100 font-medium text-primary-800 hover:bg-primary-100 dark:bg-primary-800 dark:text-primary-100 dark:hover:bg-primary-800' : 'text-surface-900'"
          @click="emit('pick', row.value)"
        >
          <td class="p-0">
            <!-- The row's click handler takes the button's click too, so a key press works -->
            <button :aria-pressed="selected === row.value" class="block w-full px-3 py-2.5 text-left" type="button">{{ row.label }}</button>
          </td>

          <td class="px-3 py-2.5 text-right font-semibold tabular-nums">{{ row.count }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script lang="ts" setup>
  import { nextTick, useTemplateRef, watch } from 'vue'
  import { dur, DURATION, EASE, gsap } from '@/app/motion'

  // A filter as a table of rows (queue filters, desktop). When filtering elsewhere adds or removes
  // rows, the table's height eases from what it was to what it is, on the emphasized curve.
  const props = defineProps<{
    label: string
    rows: { value: string | null, label: string, count: number }[]
    selected: string | null
  }>()

  const emit = defineEmits<{ pick: [value: string | null] }>()

  const box = useTemplateRef<HTMLElement>('box')

  watch(() => props.rows.length, async () => {
    const el = box.value
    if (!el) {
      return
    }
    // Where it is now, even in the middle of an earlier tween; then let it be its natural height
    const from = el.getBoundingClientRect().height
    gsap.killTweensOf(el)
    el.style.height = ''
    el.style.overflow = ''
    await nextTick()
    const to = el.getBoundingClientRect().height
    if (Math.abs(from - to) < 1) {
      return
    }
    gsap.fromTo(
      el,
      { height: from, overflow: 'hidden' },
      { height: to, duration: dur(DURATION.height), ease: EASE.emphasized, clearProps: 'height,overflow' },
    )
  }, { flush: 'pre' })
</script>
