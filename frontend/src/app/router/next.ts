/**
 * The saved `next` page, if it is safe to go to: a path in this app, never another site
 * (`//evil.example`, `https://…`, `/\evil`) and never a public auth page.
 */
export function safeNext (raw: unknown): string | null {
  const value = Array.isArray(raw) ? raw[0] : raw
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) {
    return null
  }
  const path = value.split(/[?#]/, 1)[0] ?? ''
  if (['/login', '/register', '/forgot-password'].includes(path) || path.startsWith('/register/')
    || path.startsWith('/reset-password/') || path.startsWith('/invite/')) {
    return null
  }
  return value
}
