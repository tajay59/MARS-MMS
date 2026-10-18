import type { OrgOut } from '@/api/models'
import { describe, expect, it } from 'vitest'
import { closestOrg, similarity } from '../orgMatch'

function org (name: string, status = 'active'): OrgOut {
  return { id: name, name, country: 'JM', contact_email: null, phone: null, address: null, status, version: 1 }
}

// AFD J1 step 4: suggest the organization that matches what the client typed.
describe('closestOrg', () => {
  const orgs = [org('Caribbean Weather Services Ltd'), org('Port Authority of Jamaica'), org('Northern Agriculture Co-op', 'inactive')]

  it('ignores case, punctuation and company suffixes', () => {
    expect(similarity('Caribbean Weather Services', 'Caribbean Weather Services Ltd')).toBe(1)
    expect(closestOrg('caribbean weather services', orgs)?.name).toBe('Caribbean Weather Services Ltd')
  })

  it('matches accented and plain spellings', () => {
    expect(similarity('Météo Services', 'Meteo Services')).toBe(1)
  })

  it('finds no match for a different name', () => {
    expect(closestOrg('Island Telecom', orgs)).toBeNull()
  })

  it('never suggests an inactive organization', () => {
    expect(closestOrg('Northern Agriculture Co-op', orgs)).toBeNull()
  })
})
