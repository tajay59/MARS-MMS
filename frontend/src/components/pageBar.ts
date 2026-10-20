import type { InjectionKey, Ref } from 'vue'

// The strip at the bottom of a page's pinned header on phones (PageBody `stacked`). A page may
// teleport its tab bar into it, so the tabs stay at the top while the page scrolls under them.
export const pageBarKey: InjectionKey<Ref<HTMLElement | null>> = Symbol('page-bar')
