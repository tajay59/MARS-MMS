import type { ComputedRef, InjectionKey, Ref } from 'vue'
import { inject, onBeforeUnmount, watchEffect } from 'vue'

/*
  The app shell's interactive pane (DBD "The app shell"). A page puts its list or its controls
  there with <PaneContent>, and says when a record is open, so a phone shows the record alone.
*/

export interface PaneContext {
  /** Where <PaneContent> teleports to; null until the shell has mounted. */
  target: Ref<HTMLElement | null>
  /** How many <PaneContent> blocks the current page has. */
  blocks: Ref<number>
  /** The page asked for its pane to stay at the top of the screen on phones (see PaneContent `pin`). */
  pinned: Ref<boolean>
  /** A record is open in the view: phones show the view alone, with a Back button. */
  selected: Ref<boolean>
  /** The person hid the pane (from 1024 px). */
  collapsed: Ref<boolean>
  /** The pane is hidden by the person and can be shown again from the view's header. */
  canExpand: ComputedRef<boolean>
  toggle: () => void
}

export const paneKey: InjectionKey<PaneContext> = Symbol('pane')

/** Which shell a page is in: the field shell has its own top bar and no pane. */
export const shellKey: InjectionKey<'app' | 'field'> = Symbol('shell')

export function usePane (): PaneContext | null {
  return inject(paneKey, null)
}

/** Tells the shell whether the page has a record open (for the phone's list → record step). */
export function usePaneSelection (isOpen: () => boolean): void {
  const pane = usePane()
  if (!pane) {
    return
  }
  watchEffect(() => {
    pane.selected.value = isOpen()
  })
  onBeforeUnmount(() => {
    pane.selected.value = false
  })
}
