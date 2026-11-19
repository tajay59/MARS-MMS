import type { RequestStatus } from '@/api/models'

/*
  The client guide's outline and status table (W23-5, approved mock-up "MARS-MMS Client Guide").
  Words follow the app: statuses as in PRD §5, buttons as in AFD J3, J8 and J9.
*/

export interface GuideSection {
  id: string
  title: string
}

export const SECTIONS: readonly GuideSection[] = [
  { id: 'sign-in', title: 'Sign in for the first time' },
  { id: 'report', title: 'Report a problem' },
  { id: 'follow', title: 'Follow the work' },
  { id: 'review', title: 'Review and sign off' },
  { id: 'own-report', title: 'Add your own report' },
  { id: 'stations', title: 'Your stations' },
  { id: 'emails', title: 'Emails and notifications' },
]

export interface StatusRow {
  status: RequestStatus
  means: string
  /** What the client can do while the request has this status. */
  can: string
}

export const STATUS_ROWS: readonly StatusRow[] = [
  { status: 'submitted', means: 'We have your request and an admin will look at it.', can: 'Edit or cancel it' },
  { status: 'approved', means: 'We will do the work. A technician is being chosen.', can: 'Edit or cancel it' },
  { status: 'assigned', means: 'A technician has it. Their name is on the request.', can: 'Edit or cancel it' },
  { status: 'scheduled', means: 'A visit is planned. The date is on the Visits tab.', can: 'Comment' },
  { status: 'in_progress', means: 'A technician is at the station, or the visit report is being written.', can: 'Comment' },
  { status: 'client_review', means: 'The work is done and the reports are final. It is your turn.', can: 'Review and sign off' },
  { status: 'reopened', means: 'You sent the work back. It returns to the same technicians straight away.', can: 'Comment' },
  { status: 'closed', means: 'Finished. The close-out report is on the Reports tab.', can: 'Read the reports' },
  { status: 'denied', means: 'We will not do this work. The reason is on the request.', can: 'Comment, or report it again' },
  { status: 'cancelled', means: 'The request was withdrawn.', can: 'Nothing more to do' },
]

/** Reminder days and the automatic close, from the review clock (OPS_REVIEW_REMINDER_DAYS, OPS_AUTO_CLOSE_DAYS). */
export const REVIEW_CLOCK: readonly { day: number, label: string }[] = [
  { day: 0, label: 'Work ready for review' },
  { day: 7, label: 'First reminder' },
  { day: 21, label: 'Second reminder' },
  { day: 28, label: 'Last reminder' },
  { day: 30, label: 'Closed for you' },
]

/** The section nearest the top of the reading area: the last one whose top has passed `line`. */
export function currentSection (tops: readonly number[], line: number): number {
  let current = 0
  for (const [index, top] of tops.entries()) {
    if (top <= line) {
      current = index
    }
  }
  return current
}
