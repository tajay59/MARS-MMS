import type { ReportOut, ReportSignature } from '@/api/models'
import { describe, expect, it } from 'vitest'
import {
  BODY_LIMIT,
  clearedBecause,
  type Content,
  contentOf,
  factsOf,
  leadSigned,
  mayEdit,
  mayFinalize,
  mayReopen,
  maySign,
  photoGroups,
  statusLabel,
  stoppedWords,
} from '../editor/rules'

const LEAD = { id: 'lead', isAdmin: false }
const HELPER = { id: 'helper', isAdmin: false }
const ADMIN = { id: 'admin', isAdmin: true }

function signature (signer: string, over: Partial<ReportSignature> = {}): ReportSignature {
  return {
    id: `s-${signer}`,
    signer_id: signer,
    signer_name: signer,
    typed_name: signer,
    role: signer === 'lead' ? 'lead' : 'attending',
    attestation: 'I confirm.',
    signed_at: '2026-10-05T17:00:00Z',
    content_version: 1,
    valid: true,
    ...over,
  }
}

function report (over: Partial<ReportOut> = {}): ReportOut {
  return { status: 'draft', version: 1, staff_ids: ['lead', 'helper'], lead_staff_id: 'lead', signatures: [], ...over } as ReportOut
}

function element (id: string, over: Record<string, unknown> = {}) {
  return { id, kind: 'note', title: id, description: null, items: [], priority: null, shared: true, config_versions: [], media: { main: [] }, ...over }
}

function content (): Content {
  return {
    facts: {
      visit: { staff: [{ id: 'lead', name: 'Devon Brown' }], lead_staff_id: 'lead' },
      stations: [{
        station_id: 's1',
        code: 'TST-001',
        name: 'Test Hill',
        elements: [
          element('task', { kind: 'task', title: 'Replace the funnel', items: [{ id: 'a', text: 'Remove', done: true }, { id: 'b', text: 'Level', done: false }], media: { before: [{ media_id: 'p1', kind: 'image', filename: 'IMG_1.jpg' }], after: [] } }),
          element('gate', { title: 'Gate notes', shared: false }),
          element('rec', { kind: 'recommendation', title: 'Trim the tree', priority: 'high' }),
        ],
      }],
    },
    narrative: { summary: '', recommendations: '', follow_up: '', stations: [{ station_id: 's1', work_performed: '' }] },
    media_selection: [{ station_id: 's1', element_id: 'task', section: 'before', media_id: 'p1', caption: 'Before', in_body: true }],
  } as unknown as Content
}

describe('who may do what', () => {
  it('lets attending staff and admins edit a draft and nobody edit anything else', () => {
    expect(mayEdit(report(), HELPER)).toBe(true)
    expect(mayEdit(report(), ADMIN)).toBe(true)
    expect(mayEdit(report(), { id: 'other', isAdmin: false })).toBe(false)
    expect(mayEdit(report({ status: 'finalizing' }), LEAD)).toBe(false)
    expect(mayEdit(report({ status: 'final' }), ADMIN)).toBe(false)
  })

  it('lets only people who attended sign, once each, and an admin who did not attend never', () => {
    expect(maySign(report(), LEAD)).toBe(true)
    expect(maySign(report(), ADMIN)).toBe(false)
    expect(maySign(report({ signatures: [signature('lead')] }), LEAD)).toBe(false)
    expect(maySign(report({ signatures: [signature('lead', { valid: false })] }), LEAD)).toBe(true)
    expect(maySign(report({ status: 'final' }), LEAD)).toBe(false)
  })

  it('lets the lead or an admin finalize once the lead has a valid signature', () => {
    const unsigned = report({ signatures: [signature('helper')] })
    const signed = report({ signatures: [signature('lead')] })
    expect(leadSigned(unsigned)).toBe(false)
    expect(mayFinalize(unsigned, LEAD)).toBe(false)
    expect(mayFinalize(signed, LEAD)).toBe(true)
    expect(mayFinalize(signed, ADMIN)).toBe(true)
    expect(mayFinalize(signed, HELPER)).toBe(false)
    expect(mayFinalize(report({ signatures: [signature('lead', { valid: false })] }), LEAD)).toBe(false)
    expect(mayFinalize({ ...signed, status: 'finalizing' }, LEAD)).toBe(false)
  })

  it('lets only an admin reopen a final report', () => {
    expect(mayReopen(report({ status: 'final' }), ADMIN)).toBe(true)
    expect(mayReopen(report({ status: 'final' }), LEAD)).toBe(false)
    expect(mayReopen(report({ status: 'superseded' }), ADMIN)).toBe(false)
    expect(mayReopen(report(), ADMIN)).toBe(false)
  })
})

describe('the board as the report sees it', () => {
  it('reads the content once the draft is prepared', () => {
    expect(contentOf({ content: {} } as ReportOut)).toBeNull()
    expect(contentOf({ content: content() } as unknown as ReportOut)).not.toBeNull()
  })

  it('says for each element whether it prints, with its facts', () => {
    const facts = factsOf(content())
    expect(facts.map(f => [f.title, f.printed])).toEqual([['Replace the funnel', true], ['Gate notes', false], ['Trim the tree', true]])
    expect(facts[0]!.line).toBe('Task · shared · 1 of 2 items done · not finished · 1 file')
    expect(facts[1]!.line).toBe('Note · staff only')
    expect(facts[2]!.line).toBe('Recommendation · shared · high')
  })

  it('groups the photos by station and says when the body is full', () => {
    const [group] = photoGroups(content())
    expect(group).toMatchObject({ code: 'TST-001', inBody: 1, full: false })
    expect(group!.photos[0]).toMatchObject({ filename: 'IMG_1.jpg', caption: 'Before', inBody: true })
    const crowded = content()
    crowded.media_selection = Array.from({ length: BODY_LIMIT }, (_, n) => ({ station_id: 's1', element_id: 'task', section: 'before', media_id: `p${n}`, caption: null, in_body: true }))
    expect(photoGroups(crowded)[0]).toMatchObject({ inBody: BODY_LIMIT, full: true })
    const none = content()
    none.media_selection = []
    expect(photoGroups(none)).toEqual([])
  })
})

describe('words', () => {
  it('says why a signature was cleared', () => {
    const people = { u1: 'Andrea Clarke' }
    expect(clearedBecause({ cleared_by: 'facts' }, people)).toBe('a fact changed on the board')
    expect(clearedBecause({ cleared_by: 'reopen' }, people)).toBe('the report was reopened')
    expect(clearedBecause({ cleared_by: 'u1' }, people)).toBe('report edited by Andrea Clarke')
    expect(clearedBecause({ cleared_by: 'unknown' }, people)).toBe('the report was edited')
  })

  it('says why a finalize stopped, or nothing', () => {
    expect(stoppedWords('facts_changed')).toMatchObject({ tone: 'warning', title: 'Finalizing stopped because the board changed.' })
    expect(stoppedWords('lock_failed')?.tone).toBe('error')
    expect(stoppedWords('render_failed')?.title).toBe('The PDF couldn’t be made.')
    expect(stoppedWords(null)).toBeNull()
    expect(stoppedWords('something_new')).toBeNull()
  })

  it('writes a version as status and number', () => {
    expect(statusLabel({ status: 'draft', version: 1 })).toBe('Draft v1')
    expect(statusLabel({ status: 'superseded', version: 2 })).toBe('Superseded v2')
    expect(statusLabel({ status: 'final', version: 3 })).toBe('Final v3')
  })
})
