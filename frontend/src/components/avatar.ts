/** Up to two initials: the first letters of the first and last words ("Naruto Uzumaki" → "NU"). */
export function initialsOf (name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) {
    return '?'
  }
  const first = Array.from(words[0]!)[0] ?? ''
  const last = words.length > 1 ? Array.from(words.at(-1)!)[0] ?? '' : ''
  return (first + last).toLocaleUpperCase()
}

/** A stable choice among `count` for a seed (FNV-1a), so a person keeps the same gradient. */
export function pickOf (seed: string, count: number): number {
  let hash = 0x81_1C_9D_C5
  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.codePointAt(i)!
    hash = Math.imul(hash, 0x01_00_01_93)
  }
  return (hash >>> 0) % count
}
