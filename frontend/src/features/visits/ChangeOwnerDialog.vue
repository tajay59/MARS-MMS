<template>
  <ModalSheet v-model="open" labelledby="co-h" max-width="460" persistent>
    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <h2 id="co-h" class="m-0 text-h2 text-surface-900">Change owner</h2>

      <p v-if="station" class="m-0 text-surface-900">{{ station.station_name }} (<span class="font-mono text-sm" translate="no">{{ station.station_code }}</span>)</p>

      <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

      <FormField id="co-owner" label="New owner">
        <v-select
          id="co-owner"
          v-model="owner"
          item-title="label"
          item-value="id"
          :items="items"
          name="owner"
        />
      </FormField>

      <p class="m-0 text-sm text-surface-600">
        <template v-if="station && owner !== station.owner.id">{{ station.owner.name }} and {{ nameOf(owner) }} are both told. </template>Needs a connection.
      </p>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="open = false">Keep it</v-btn>
        <v-btn color="primary" :disabled="!station || owner === station.owner.id" :loading="busy" type="submit">Change owner</v-btn>
      </div>
    </form>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { VisitOut } from '@/api/models'
  import { computed, ref, watch } from 'vue'
  import { visitsApi } from '@/api/operations'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { failureOf } from './failures'

  // Change owner (PRD VIS-3; AFD J5 step 5b; ADR-18): who writes a station's work record on this
  // visit. Planned: any of the people attending. Started: the lead or an admin changes it. One owner
  // per station: the old owner's work stays theirs until the change.
  const props = defineProps<{ visit: VisitOut, stationId: string | null }>()

  const emit = defineEmits<{ done: [visit: VisitOut], changed: [] }>()
  const open = defineModel<boolean>({ required: true })

  const owner = ref('')
  const problem = ref<string | null>(null)
  const busy = ref(false)

  const station = computed(() => props.visit.stations.find(s => s.station_id === props.stationId))
  const items = computed(() => props.visit.staff.map(p => ({
    id: p.id,
    label: p.id === props.visit.lead.id ? `${p.name} (lead)` : p.name,
  })))

  function nameOf (id: string): string {
    return props.visit.staff.find(p => p.id === id)?.name ?? ''
  }

  watch([open, () => props.stationId], () => {
    if (open.value) {
      owner.value = station.value?.owner.id ?? ''
      problem.value = null
    }
  }, { immediate: true })

  async function submit (): Promise<void> {
    if (!station.value || busy.value || owner.value === station.value.owner.id) {
      return
    }
    busy.value = true
    problem.value = null
    try {
      // A planned visit's `stations` is the whole list; a started one takes only the owners that change
      const stations = props.visit.status === 'planned'
        ? props.visit.stations.map(s => ({ station_id: s.station_id, owner_staff_id: s.station_id === station.value!.station_id ? owner.value : s.owner.id }))
        : [{ station_id: station.value.station_id, owner_staff_id: owner.value }]
      const done = await visitsApi.update(props.visit.id, { stations, version: props.visit.version })
      open.value = false
      emit('done', done)
    } catch (error) {
      const failure = failureOf(error, 'We couldn’t change the owner. Try again in a moment.')
      problem.value = failure.message
      if (failure.reload) {
        emit('changed')
      }
    } finally {
      busy.value = false
    }
  }
</script>
