import { describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'
import { useLeaveGuard } from '../useLeaveGuard'

describe('useLeaveGuard', () => {
  it('lets the person leave at once when nothing changed', async () => {
    const { askLeave, confirmLeave } = useLeaveGuard(ref(false))
    await expect(confirmLeave()).resolves.toBe(true)
    expect(askLeave.value).toBe(false)
  })

  it('asks first when there are unsaved changes, and leaves on "Leave"', async () => {
    const { askLeave, confirmLeave, leave } = useLeaveGuard(ref(true))
    const answer = confirmLeave()
    expect(askLeave.value).toBe(true)
    leave()
    await expect(answer).resolves.toBe(true)
    expect(askLeave.value).toBe(false)
  })

  it('keeps editing when the dialog closes without "Leave" (Escape, click outside)', async () => {
    const { askLeave, confirmLeave } = useLeaveGuard(ref(true))
    const answer = confirmLeave()
    await nextTick() // the dialog is on screen before it is dismissed
    askLeave.value = false
    await nextTick()
    await expect(answer).resolves.toBe(false)
  })

  it('reads a getter as well as a ref', async () => {
    let changed = false
    const { confirmLeave } = useLeaveGuard(() => changed)
    await expect(confirmLeave()).resolves.toBe(true)
    changed = true
    const { askLeave, confirmLeave: ask } = useLeaveGuard(() => changed)
    void ask()
    expect(askLeave.value).toBe(true)
  })

  it('answers "stay" to the first question when a second route change comes in', async () => {
    const { confirmLeave, leave } = useLeaveGuard(ref(true))
    const first = confirmLeave()
    const second = confirmLeave()
    await expect(first).resolves.toBe(false)
    leave()
    await expect(second).resolves.toBe(true)
  })
})
