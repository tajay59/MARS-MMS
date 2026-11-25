import type { Preferences } from '@/api/models'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createVuetify } from 'vuetify'
import { notificationsApi } from '@/api/notifications'
import { ApiError } from '@/api/problem'
import EmailPreferences from '../EmailPreferences.vue'

vi.mock('@/api/notifications', () => ({
  notificationsApi: { preferences: vi.fn(), savePreferences: vi.fn() },
}))

function stored (email: boolean): Preferences {
  return {
    groups: [{
      label: 'Calibration',
      items: [{ key: 'calibration.digest', label: 'Weekly digest of calibrations due', hint: 'Mondays', email }],
    }],
  }
}

const SWITCH = '[id="ep-calibration.digest"]'

async function render () {
  const wrapper = mount(EmailPreferences, { global: { plugins: [createVuetify()] } })
  await flushPromises()
  return { wrapper, input: () => wrapper.get<HTMLInputElement>(SWITCH).element }
}

describe('EmailPreferences (PRD NOT-4)', () => {
  beforeEach(() => {
    vi.mocked(notificationsApi.preferences).mockReset().mockImplementation(async () => stored(true))
    vi.mocked(notificationsApi.savePreferences).mockReset()
  })

  it('turns the switch at once, before the server answers', async () => {
    let answer!: (value: Preferences) => void
    vi.mocked(notificationsApi.savePreferences).mockReturnValue(new Promise(resolve => {
      answer = resolve
    }))
    const { wrapper, input } = await render()
    expect(input().checked).toBe(true)

    await wrapper.get(SWITCH).setValue(false)
    expect(input().checked).toBe(false)
    expect(notificationsApi.savePreferences).toHaveBeenCalledWith({ 'calibration.digest': false })

    answer(stored(false))
    await flushPromises()
    expect(input().checked).toBe(false)
    expect(wrapper.text()).toContain('Saved')
  })

  it('goes back to what is stored when the save fails', async () => {
    vi.mocked(notificationsApi.savePreferences).mockRejectedValue(
      new ApiError(422, { detail: 'That email type is not yours to change.' }),
    )
    const { wrapper, input } = await render()

    await wrapper.get(SWITCH).setValue(false)
    await flushPromises()
    expect(input().checked).toBe(true)
    expect(wrapper.text()).toContain('That email type is not yours to change.')
  })
})
