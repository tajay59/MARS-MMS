import type { OrgOut } from '@/api/models'

/*
  The existing organization closest to the name a client typed at registration (AFD J1 step 4).
  Only a suggestion: the admin confirms it. Compares words after dropping case, punctuation and
  company suffixes, so "Caribbean Weather Services" matches "Caribbean Weather Services Ltd".
*/

const SUFFIXES = new Set(['ltd', 'limited', 'inc', 'llc', 'plc', 'co', 'company', 'corp', 'corporation', 'the', 'of', 'and'])

function words (name: string): Set<string> {
  return new Set(
    name
      .toLowerCase()
      .normalize('NFKD')
      .replace(/\p{M}/gu, '')
      .split(/[^a-z0-9]+/)
      .filter(w => w && !SUFFIXES.has(w)),
  )
}

/** Share of words in common (Jaccard), 0–1. */
export function similarity (a: string, b: string): number {
  const x = words(a)
  const y = words(b)
  if (x.size === 0 || y.size === 0) {
    return 0
  }
  let common = 0
  for (const w of x) {
    if (y.has(w)) {
      common += 1
    }
  }
  return common / (x.size + y.size - common)
}

/** The best active match at or above `threshold`, or null. */
export function closestOrg (typed: string, orgs: OrgOut[], threshold = 0.5): OrgOut | null {
  let best: OrgOut | null = null
  let score = threshold
  for (const org of orgs) {
    if (org.status !== 'active') {
      continue
    }
    const s = similarity(typed, org.name)
    if (s >= score) {
      best = org
      score = s
    }
  }
  return best
}
