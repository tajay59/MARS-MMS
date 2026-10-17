import { nextTick } from 'vue'

/** After a failed submit, move focus to the first field with an error (WCAG 3.3.1). */
export async function focusFirstError (): Promise<void> {
  await nextTick()
  document
    .querySelector<HTMLElement>('.v-input--error input, .v-input--error textarea, [aria-invalid="true"]')
    ?.focus()
}
