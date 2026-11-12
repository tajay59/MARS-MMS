import { formatDate } from '@/app/format'

/*
  Two-step sign-in, the rules the screens share (W22; PRD AUTH-14). No Vue here, so they are
  tested on their own. The server decides everything; this only words it.
*/

export interface SetupBanner {
  type: 'warning' | 'error'
  /** The bold first sentence. */
  lead: string
  rest: string
}

/**
  The nudge for a person whose role needs two-step sign-in and who has none yet. `requiredBy` is
  the end of their setup window. The wording gets firmer as it nears, and says what is true after
  it passes: the rule applies at the next login, so nobody is cut off in the middle of a visit.
*/
export function setupBanner (requiredBy: string, now: Date = new Date(), timeZone?: string | null): SetupBanner {
  const end = new Date(requiredBy)
  if (Number.isNaN(end.getTime()) || end.getTime() <= now.getTime()) {
    return {
      type: 'error',
      lead: 'Two-step sign-in isn’t set up.',
      rest: 'You’ll need it the next time you log in.',
    }
  }
  const today = formatDate(now.toISOString(), timeZone) === formatDate(requiredBy, timeZone)
  return today
    ? {
        type: 'warning',
        lead: 'Set up two-step sign-in today.',
        rest: 'After today, you can’t log in without it.',
      }
    : {
        type: 'warning',
        lead: `Set up two-step sign-in by ${formatDate(requiredBy, timeZone)}.`,
        rest: 'After that, you can’t log in without it.',
      }
}

/** The recovery codes as a text file the person keeps, with what they are for. */
export function recoveryCodesText (codes: readonly string[], email: string, madeOn: string): string {
  return [
    `MARS-MMS recovery codes for ${email}`,
    `Made on ${madeOn}`,
    '',
    'Each code lets you log in once if you lose your phone. Keep this file somewhere safe.',
    'Making new codes in My profile stops these from working.',
    '',
    ...codes,
    '',
  ].join('\n')
}

/** `JBSWY3DPEHPK3PXP` as `JBSW Y3DP EHPK 3PXP`, the way people type a key by hand. */
export function groupKey (secret: string): string {
  return secret.replaceAll(/(.{4})(?=.)/g, '$1 ')
}
