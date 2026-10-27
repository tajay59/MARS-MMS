<template>
  <section aria-labelledby="sp-h" class="flex flex-col gap-3 rounded-card border border-surface-200 bg-surface p-4">
    <h2 id="sp-h" class="m-0 text-h4 text-surface-900">Signatures</h2>

    <FeedbackBanner v-if="clearedAt" type="warning">
      <b class="font-semibold">Cleared at {{ clearedAt }}.</b> {{ clearedWhy }}
    </FeedbackBanner>

    <ul class="m-0 flex list-none flex-col p-0">
      <li v-for="row in rows" :key="row.key" class="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 border-t border-surface-200 py-3 first:border-t-0 first:pt-0">
        <div class="min-w-0" :class="row.cleared ? 'text-surface-600' : ''">
          <strong class="font-medium" :class="row.cleared ? 'line-through decoration-1' : 'text-surface-900'">{{ row.name }}</strong>

          <v-chip
            v-if="row.lead"
            class="ml-2"
            color="primary"
            label
            size="x-small"
            variant="tonal"
          >Lead</v-chip>

          <div class="text-xs text-surface-600">{{ row.note }}</div>
        </div>

        <img
          v-if="row.image"
          :alt="`Drawn signature of ${row.name}`"
          class="h-10 w-30 object-contain"
          :src="row.image"
        >

        <v-btn
          v-else-if="row.canSign"
          :color="row.lead ? 'primary' : undefined"
          :variant="row.lead ? 'flat' : 'outlined'"
          @click="emit('sign')"
        >{{ row.cleared ? 'Sign again' : 'Sign' }}</v-btn>
      </li>
    </ul>

    <p v-if="!attended && editable" class="m-0 text-sm text-surface-700">You did not attend this visit, so there is no Sign button for you.</p>
    <p class="m-0 text-xs text-surface-600">Signing needs a connection. Any change to the report clears the signatures.</p>
  </section>
</template>

<script lang="ts" setup>
  import type { Who } from './rules'
  import type { ReportOut, ReportSignature } from '@/api/models'
  import { computed } from 'vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { formatWhen } from '../../visits'
  import { clearedBecause, mySignature } from './rules'

  // The signatures of the version on screen (W17, RPT-4, W17-4): who has signed with their drawing,
  // who has not, and the ones that were cleared and why. Cleared signatures stay in the list so the
  // lead can see what was lost. `people` maps an id to a name.
  const props = defineProps<{
    report: ReportOut
    who: Who
    people: Record<string, string>
    editable: boolean
    attended: boolean
    zone?: string | null
  }>()

  const emit = defineEmits<{ sign: [] }>()

  interface Row {
    key: string
    name: string
    lead: boolean
    note: string
    image: string | null
    cleared: boolean
    canSign: boolean
  }

  const mine = computed(() => mySignature(props.report, props.who))

  function when (sig: ReportSignature): string {
    return formatWhen(sig.signed_at, props.zone ?? undefined)
  }

  // One row per attending person: their valid signature, else the last one cleared, else nothing yet
  const rows = computed<Row[]>(() => {
    const report = props.report
    return report.staff_ids.map(id => {
      const mineRows = report.signatures.filter(s => s.signer_id === id)
      const valid = mineRows.find(s => s.valid)
      const cleared = mineRows.findLast(s => !s.valid)
      const lead = id === report.lead_staff_id
      const name = props.people[id] ?? 'Someone on the visit'
      if (valid) {
        return { key: id, name, lead, note: `Signed ${when(valid)}`, image: valid.image ?? null, cleared: false, canSign: false }
      }
      const canSign = props.editable && props.attended && id === props.who.id && !mine.value
      if (cleared) {
        return { key: id, name, lead, note: `Cleared · ${clearedBecause(cleared, props.people)}`, image: null, cleared: true, canSign }
      }
      return { key: id, name, lead, note: lead ? 'Needed to finalize' : 'Has not signed. Optional.', image: null, cleared: false, canSign }
    })
  })

  const lastCleared = computed(() => props.report.signatures
    .filter(s => !s.valid && s.cleared_at)
    .toSorted((a, b) => (b.cleared_at ?? '').localeCompare(a.cleared_at ?? ''))[0])
  // The banner shows only while nothing is signed again
  const clearedAt = computed(() => lastCleared.value && !props.report.signatures.some(s => s.valid) && lastCleared.value.cleared_at
    ? formatWhen(lastCleared.value.cleared_at, props.zone ?? undefined)
    : '')
  const clearedWhy = computed(() => lastCleared.value
    ? `${lastCleared.value.cleared_by === 'facts' ? 'A fact changed on the board' : 'The report was edited'} after it was signed. Everyone has to sign again.`
    : '')
</script>
