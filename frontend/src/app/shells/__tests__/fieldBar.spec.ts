import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { fieldBar, useFieldBar } from '../fieldBar'

describe('the field shell’s top bar', () => {
  it('is named by the page while it is open, and goes back to the route’s title after', () => {
    const Page = defineComponent({
      setup () {
        useFieldBar(() => ({ title: 'Kingston Harbour', back: { name: 'visits' }, backLabel: 'Back to the stations' }))
        return () => h('div')
      },
    })
    expect(fieldBar.title).toBeNull()
    const page = mount(Page)
    expect(fieldBar.title).toBe('Kingston Harbour')
    expect(fieldBar.back).toEqual({ name: 'visits' })
    expect(fieldBar.backLabel).toBe('Back to the stations')
    page.unmount()
    expect(fieldBar.title).toBeNull()
    expect(fieldBar.back).toBeNull()
    expect(fieldBar.backLabel).toBe('Back')
  })
})
