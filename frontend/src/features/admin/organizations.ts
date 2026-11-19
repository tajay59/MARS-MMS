import type { OrgIn, OrgOut, OrgPatch, UserOut } from '@/api/models'

/*
  The rules of /admin/organizations (PRD ORG-1, ORG-4), with no Vue: which organizations the table
  shows, how many people each has, and what the drawer's form sends. The limits match auth's
  schemas (app/api/schemas.py), so the form says what is wrong before the server does.
*/

export type OrgFilter = 'active' | 'inactive' | 'all'

export const ORG_FILTERS: readonly { value: OrgFilter, label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'inactive', label: 'Inactive' },
  { value: 'all', label: 'All' },
]

export function isOrgFilter (value: unknown): value is OrgFilter {
  return ORG_FILTERS.some(f => f.value === value)
}

export function countByStatus (orgs: readonly OrgOut[], filter: OrgFilter): number {
  return filter === 'all' ? orgs.length : orgs.filter(o => o.status === filter).length
}

function fold (text: string): string {
  return text.normalize('NFKD').replaceAll(/\p{M}/gu, '').toLowerCase().trim()
}

/** The rows for a filter and a search on name, short name or the earlier system's ID, by name. */
export function visibleOrgs (orgs: readonly OrgOut[], filter: OrgFilter, search: string): OrgOut[] {
  const q = fold(search)
  return orgs
    .filter(o => filter === 'all' || o.status === filter)
    .filter(o => !q || [o.name, o.short_name, o.external_id].some(v => v && fold(v).includes(q)))
    .toSorted((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }))
}

/** People who can (or could) sign in for each organization: invited, active or disabled clients. */
export function peopleByOrg (users: readonly UserOut[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const u of users) {
    if (u.org_id && u.status !== 'pending' && u.status !== 'rejected') {
      counts.set(u.org_id, (counts.get(u.org_id) ?? 0) + 1)
    }
  }
  return counts
}

export function peopleText (count: number): string {
  if (count === 0) {
    return 'No people yet'
  }
  return count === 1 ? '1 person' : `${count} people`
}

export interface OrgForm {
  name: string
  shortName: string
  externalId: string
  country: string | null
  contactEmail: string
  phone: string
  address: string
}

export function emptyForm (): OrgForm {
  return { name: '', shortName: '', externalId: '', country: null, contactEmail: '', phone: '', address: '' }
}

export function formFrom (org: OrgOut): OrgForm {
  return {
    name: org.name,
    shortName: org.short_name ?? '',
    externalId: org.external_id ?? '',
    country: org.country,
    contactEmail: org.contact_email ?? '',
    phone: org.phone ?? '',
    address: org.address ?? '',
  }
}

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s.]{2,}$/
const EXTERNAL_ID = /^[\w.:-]{1,64}$/

/** What is wrong with the form, by the API's field names; empty when it can be sent. */
export function checkForm (form: OrgForm): Record<string, string> {
  const found: Record<string, string> = {}
  const name = form.name.trim()
  if (!name) {
    found.name = 'Enter the organization’s name'
  } else if (name.length > 200) {
    found.name = 'Use 200 characters or fewer'
  }
  if (form.shortName.trim().length > 40) {
    found.short_name = 'Use 40 characters or fewer'
  }
  const ext = form.externalId.trim()
  if (ext && !EXTERNAL_ID.test(ext)) {
    found.external_id = 'Use letters, numbers and . _ : - only, up to 64'
  }
  if (!form.country) {
    found.country = 'Choose the country'
  }
  const email = form.contactEmail.trim()
  if (email && !EMAIL.test(email)) {
    found.contact_email = 'Enter a valid email, or leave it empty'
  }
  if (form.phone.trim().length > 40) {
    found.phone = 'Use 40 characters or fewer'
  }
  if (form.address.trim().length > 500) {
    found.address = 'Use 500 characters or fewer'
  }
  return found
}

function optional (text: string): string | null {
  return text.trim() || null
}

/** The body of POST /organizations. */
export function toCreate (form: OrgForm): OrgIn {
  return {
    name: form.name.trim(),
    short_name: optional(form.shortName),
    external_id: optional(form.externalId),
    country: form.country ?? '',
    contact_email: optional(form.contactEmail),
    phone: optional(form.phone),
    address: optional(form.address),
  }
}

/** The body of PATCH /organizations/{id}: only what changed, or null when nothing did. */
export function toPatch (org: OrgOut, form: OrgForm): OrgPatch | null {
  const next = toCreate(form)
  const before: OrgIn = {
    name: org.name,
    short_name: org.short_name,
    external_id: org.external_id,
    country: org.country,
    contact_email: org.contact_email,
    phone: org.phone,
    address: org.address,
  }
  const changed: Partial<OrgIn> = {}
  for (const key of Object.keys(next) as (keyof OrgIn)[]) {
    if ((next[key] ?? null) !== (before[key] ?? null)) {
      Object.assign(changed, { [key]: next[key] })
    }
  }
  return Object.keys(changed).length === 0 ? null : { version: org.version, ...changed }
}

/** A 409 from the server, as a message on the field it is about. */
export function conflictField (code: string | null | undefined): Record<string, string> | null {
  if (code === 'org_name_taken') {
    return { name: 'An organization with this name already exists' }
  }
  if (code === 'org_external_id_taken') {
    return { external_id: 'Another organization already has this ID' }
  }
  return null
}
