<template>
  <p v-if="names" class="m-0 rounded-lg bg-surface-50 px-3.5 py-3 text-sm text-surface-900 shadow-[inset_3px_0_0_var(--v-theme-primary)]" role="status">
    <strong>This visit is prepared on {{ names }}’s {{ many ? 'phones' : 'phone' }}.</strong> Work not yet synced from {{ many ? 'them' : 'it' }} may come back as a conflict.
  </p>
</template>

<script lang="ts" setup>
  import type { VisitOut } from '@/api/models'
  import { computed } from 'vue'

  // The sentence the people who plan a visit see (W14-14, OFF-9): a phone holds the visit, so a
  // change made here can meet work the phone has not sent yet. It warns; it never blocks.
  const props = defineProps<{ preparedOn?: VisitOut['prepared_on'] }>()

  const people = computed(() => [...new Set((props.preparedOn ?? []).map(entry => entry.user.name))])
  const many = computed(() => people.value.length > 1)
  const names = computed(() => {
    if (people.value.length < 2) {
      return people.value[0] ?? ''
    }
    return `${people.value.slice(0, -1).join(', ')} and ${people.value.at(-1)}`
  })
</script>
