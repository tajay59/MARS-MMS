import type { OrgOut, UserOut } from '@/api/models'
import { describe, expect, it } from 'vitest'
import {
  checkForm,
  conflictField,
  countByStatus,
  emptyForm,
  formFrom,
  isOrgFilter,
  peopleByOrg,
  peopleText,
  toCreate,
  toPatch,
  visibleOrgs,
} from '../organizations'

function org (over: Partial<OrgOut> = {}): OrgOut {
  return {
    id: 'o1', name: 'Northcoast Ports', short_name: 'NCP', external_id: 'ENT-0007', country: 'JM',
    contact_email: null, phone: null, address: null, status: 'active', version: 3, ...over,
  }
}

function user (orgId: string | null, status: string): UserOut {
  return { org_id: orgId, status } as unknown as UserOut
}

const ORGS = [
  org({ id: 'a', name: 'Southern Utilities', short_name: 'SUL', external_id: 'ENT-0044' }),
  org({ id: 'b', name: 'Île Agro', short_name: null, external_id: null, status: 'inactive' }),
  org({ id: 'c', name: 'northcoast Ports', short_name: 'NCP', external_id: 'ENT-0007' }),
]

describe('the table', () => {
  it('shows the active ones by default, by name, whatever the case', () => {
    expect(visibleOrgs(ORGS, 'active', '').map(o => o.id)).toEqual(['c', 'a'])
    expect(visibleOrgs(ORGS, 'inactive', '').map(o => o.id)).toEqual(['b'])
    expect(visibleOrgs(ORGS, 'all', '').map(o => o.id)).toEqual(['b', 'c', 'a'])
  })

  it('searches the name, the short name and the earlier system’s ID, ignoring accents', () => {
    expect(visibleOrgs(ORGS, 'all', 'ile').map(o => o.id)).toEqual(['b'])
    expect(visibleOrgs(ORGS, 'all', 'sul').map(o => o.id)).toEqual(['a'])
    expect(visibleOrgs(ORGS, 'all', ' ent-0007 ').map(o => o.id)).toEqual(['c'])
    expect(visibleOrgs(ORGS, 'active', 'agro')).toEqual([])
  })

  it('counts each status for the pane', () => {
    expect([countByStatus(ORGS, 'active'), countByStatus(ORGS, 'inactive'), countByStatus(ORGS, 'all')]).toEqual([2, 1, 3])
  })

  it('takes only known filters from the address', () => {
    expect(['active', 'inactive', 'all'].every(isOrgFilter)).toBe(true)
    expect(isOrgFilter('disabled')).toBe(false)
    expect(isOrgFilter(undefined)).toBe(false)
  })

  it('counts the people of each organization, leaving out registrations not approved', () => {
    const counts = peopleByOrg([
      user('a', 'active'), user('a', 'invited'), user('a', 'disabled'),
      user('a', 'pending'), user('a', 'rejected'), user(null, 'active'), user('c', 'active'),
    ])
    expect(counts.get('a')).toBe(3)
    expect(counts.get('c')).toBe(1)
    expect(counts.has('b')).toBe(false)
    expect([peopleText(0), peopleText(1), peopleText(4)]).toEqual(['No people yet', '1 person', '4 people'])
  })
})

describe('the form', () => {
  it('needs a name and a country, and checks the rest only when given', () => {
    expect(checkForm(emptyForm())).toEqual({ name: 'Enter the organization’s name', country: 'Choose the country' })
    expect(checkForm({ ...emptyForm(), name: 'A', country: 'JM' })).toEqual({})
  })

  it('says what is wrong in the API’s field names', () => {
    const errors = checkForm({
      ...emptyForm(), name: 'x'.repeat(201), country: 'JM', shortName: 'y'.repeat(41),
      externalId: 'ENT 7', contactEmail: 'not-an-email', phone: '1'.repeat(41), address: 'z'.repeat(501),
    })
    expect(Object.keys(errors).toSorted()).toEqual(['address', 'contact_email', 'external_id', 'name', 'phone', 'short_name'])
  })

  it('sends empty optional fields as null, trimmed', () => {
    expect(toCreate({ ...emptyForm(), name: '  Valley Trust ', country: 'JM', shortName: ' ', contactEmail: ' a@b.org ' })).toEqual({
      name: 'Valley Trust', short_name: null, external_id: null, country: 'JM',
      contact_email: 'a@b.org', phone: null, address: null,
    })
  })

  it('patches only what changed, with the version it was read at', () => {
    const current = org()
    expect(toPatch(current, formFrom(current))).toBeNull()
    expect(toPatch(current, { ...formFrom(current), phone: ' +1 876 555 0142 ', shortName: '' })).toEqual({
      version: 3, phone: '+1 876 555 0142', short_name: null,
    })
  })

  it('puts a clash on the field it is about', () => {
    expect(conflictField('org_name_taken')).toEqual({ name: 'An organization with this name already exists' })
    expect(conflictField('org_external_id_taken')).toEqual({ external_id: 'Another organization already has this ID' })
    expect(conflictField('version_conflict')).toBeNull()
  })
})
