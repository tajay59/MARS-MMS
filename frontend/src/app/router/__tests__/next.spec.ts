import { describe, expect, it } from 'vitest'
import { safeNext } from '../next'

// The saved page after login (AFD §5.2) must never send the user to another site.
describe('safeNext', () => {
  it.each([
    ['/requests/abc?tab=comments#c1', '/requests/abc?tab=comments#c1'],
    ['/admin/users', '/admin/users'],
    [['/stations'], '/stations'],
  ])('keeps %j', (raw, expected) => {
    expect(safeNext(raw)).toBe(expected)
  })

  it.each([
    'https://evil.example/',
    '//evil.example/path',
    String.raw`/\evil.example`,
    'javascript:alert(1)',
    '',
    '/login',
    '/login?next=/x',
    '/register/pending',
    '/reset-password/abc',
    '/invite/abc',
    undefined,
    42,
  ])('drops %j', raw => {
    expect(safeNext(raw)).toBeNull()
  })
})
