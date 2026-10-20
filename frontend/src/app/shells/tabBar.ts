// Classes for the items of both bottom bars (the app shell's AppTabBar and the field shell), so
// they look the same. The page open has no background: its icon and label take the brand colour
// and a dot sits below the label. Written out in full so Tailwind finds each class.
// A press shrinks the icon and lets it spring back (GSAP, instant under reduced motion); the dot
// pops in with a CSS transition, which base.css turns off under reduced motion.

import { dur, gsap } from '@/app/motion'

export const tabItem = 'group flex w-full min-w-0 flex-col items-center justify-center py-1'

export function tabIcon (active: boolean): string {
  return active
    ? 'relative flex items-center justify-center rounded-xl px-3 py-1 text-primary transition-colors duration-200'
    : 'relative flex items-center justify-center rounded-xl px-3 py-1 text-surface-600 transition-colors duration-200 group-hover:bg-surface-100 group-hover:text-surface-900'
}

export function tabLabel (active: boolean): string {
  return active
    ? 'mt-0.5 max-w-full truncate text-xs font-bold tracking-tight text-primary'
    : 'mt-0.5 max-w-full truncate text-xs font-medium tracking-tight text-surface-600 group-hover:text-surface-900'
}

// Always in the layout, so the bar doesn't change height when the page does
export function tabDot (active: boolean): string {
  return active
    ? 'mt-0.5 size-1 scale-100 rounded-full bg-primary opacity-100 transition duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)]'
    : 'mt-0.5 size-1 scale-0 rounded-full bg-primary opacity-0 transition duration-150'
}

const PRESSED = 0.78

function iconOf (event: Event): Element | null {
  return (event.currentTarget as Element).querySelector('[data-tab-icon]')
}

export function tabDown (event: PointerEvent): void {
  if (event.button === 0) {
    gsap.to(iconOf(event), { scale: PRESSED, duration: dur(0.08), overwrite: true })
  }
}

// The icon lands slightly past full size and settles (back.out)
export function tabUp (event: Event): void {
  gsap.to(iconOf(event), { scale: 1, duration: dur(0.4), ease: 'back.out(3)', overwrite: true, clearProps: 'transform' })
}

// A click from the keyboard (Enter) has no pointer events, so it gets both in one go
export function tabKey (event: MouseEvent): void {
  if (event.detail === 0) {
    gsap.timeline({ defaults: { overwrite: true } })
      .to(iconOf(event), { scale: PRESSED, duration: dur(0.07) })
      .to(iconOf(event), { scale: 1, duration: dur(0.4), ease: 'back.out(3)', clearProps: 'transform' })
  }
}
