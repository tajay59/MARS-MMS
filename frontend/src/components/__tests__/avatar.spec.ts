import { describe, expect, it } from 'vitest'
import { initialsOf, pickOf } from '@/components/avatar'

// The registration card's avatar (decision W4-13)
describe('initialsOf', () => {
  it('takes the first letters of the first and last names', () => {
    expect(initialsOf('Naruto Uzumaki')).toBe('NU')
    expect(initialsOf('  maria   del carmen  ruiz ')).toBe('MR')
    expect(initialsOf('Cher')).toBe('C')
    expect(initialsOf('Émile Zola')).toBe('ÉZ')
    expect(initialsOf('')).toBe('?')
  })
})

describe('pickOf', () => {
  it('gives one person the same gradient every time, spread over all of them', () => {
    expect(pickOf('0192f0a1-aaaa', 6)).toBe(pickOf('0192f0a1-aaaa', 6))
    const seen = new Set(Array.from({ length: 60 }, (_, i) => pickOf(`user-${i}`, 6)))
    expect(seen.size).toBe(6)
  })
})
