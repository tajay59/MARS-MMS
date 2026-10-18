/*
  Device-made IDs (CLAUDE.md rule 9): UUIDv7, so a record made offline keeps its ID for good and
  a retry can never create it twice. 48 bits of milliseconds, then random bits (RFC 9562).
*/

export const UUID7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

export function newId (now: number = Date.now()): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  const ms = BigInt(now)
  for (let i = 0; i < 6; i++) {
    bytes[i] = Number((ms >> BigInt(8 * (5 - i))) & 0xFFn)
  }
  bytes[6] = (bytes[6]! & 0x0F) | 0x70
  bytes[8] = (bytes[8]! & 0x3F) | 0x80
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
