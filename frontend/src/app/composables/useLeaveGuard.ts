import type { Ref } from 'vue'
import { ref, watch } from 'vue'

/**
 * The question a page asks before a route change throws away unsaved edits. It drives a
 * `DiscardConfirm` (`v-model="askLeave" @leave="leave"`) instead of the browser's `window.confirm`,
 * which looks different on every device and inside an installed iOS app. `confirmLeave` resolves
 * `true` when leaving is fine, so it can be returned from a router guard. Closing the dialog with
 * Escape or a click outside means "keep editing".
 */
export function useLeaveGuard (dirty: Ref<boolean> | (() => boolean)) {
  const askLeave = ref(false)
  let answer: ((leave: boolean) => void) | null = null
  const isDirty = () => typeof dirty === 'function' ? dirty() : dirty.value

  function confirmLeave (): Promise<boolean> {
    if (!isDirty()) {
      return Promise.resolve(true)
    }
    // A second route change while the question is open keeps the first question
    answer?.(false)
    askLeave.value = true
    return new Promise<boolean>(resolve => {
      answer = resolve
    })
  }

  function leave (): void {
    askLeave.value = false
    answer?.(true)
    answer = null
  }

  watch(askLeave, open => {
    if (!open && answer) {
      answer(false)
      answer = null
    }
  })

  return { askLeave, confirmLeave, leave }
}
