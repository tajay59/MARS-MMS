import type { RouteLocationRaw } from 'vue-router'
import { onBeforeUnmount, reactive, watchEffect } from 'vue'

/*
  The field shell's top bar (DBD "Field": back arrow, visit or station name, sync badge). The route's
  title is the default; a page that is about one visit or station names itself and says where Back goes.
*/

const bar = reactive<{ title: string | null, back: RouteLocationRaw | null, backLabel: string }>({
  title: null,
  back: null,
  backLabel: 'Back',
})

export const fieldBar = bar

/** Names the top bar while the page is open, and puts it back when the page goes. */
export function useFieldBar (options: () => { title?: string | null, back?: RouteLocationRaw | null, backLabel?: string }): void {
  watchEffect(() => {
    const { title, back, backLabel } = options()
    bar.title = title ?? null
    bar.back = back ?? null
    bar.backLabel = backLabel ?? 'Back'
  })
  onBeforeUnmount(() => {
    bar.title = null
    bar.back = null
    bar.backLabel = 'Back'
  })
}
