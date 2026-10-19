import type { Ref } from 'vue'
import { onBeforeUnmount, ref, watch } from 'vue'

/**
 * What every form in a `ModalSheet` shares: closing asks first while there are unsaved changes
 * (`requestClose`), and the browser warns before a reload or tab close while the form is open and
 * changed.
 */
export function useFormDialog (open: Ref<boolean>, dirty: () => boolean) {
  const askLeave = ref(false)

  function requestClose (): void {
    if (dirty()) {
      askLeave.value = true
    } else {
      open.value = false
    }
  }

  function leave (): void {
    askLeave.value = false
    open.value = false
  }

  function warnUnload (event: BeforeUnloadEvent): void {
    if (open.value && dirty()) {
      event.preventDefault()
    }
  }

  window.addEventListener('beforeunload', warnUnload)
  onBeforeUnmount(() => window.removeEventListener('beforeunload', warnUnload))
  watch(open, isOpen => {
    if (!isOpen) {
      askLeave.value = false
    }
  })

  return { askLeave, requestClose, leave }
}
