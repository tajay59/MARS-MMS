/*
  Errors from the API are RFC 9457 problem details (mms_common.errors, TP V1):
  { type, title, status, code, detail, request_id, ... } plus, by case, `reason` (401),
  `retry_after` (429) and `errors: [{ loc, msg, code? }]` (422).
*/

export interface FieldError {
  loc: (string | number)[]
  msg: string
  code?: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: string
  readonly reason: string | undefined
  readonly retryAfter: number | undefined
  readonly errors: FieldError[]
  readonly requestId: string | undefined
  /** The body field a rule of ours refused (`reason`, `station_ids`), when the server names one. */
  readonly field: string | undefined
  /** The whole problem body, for the few errors that carry more (`claimed_by` on a lost claim). */
  readonly body: Record<string, unknown>

  constructor (status: number, body: Record<string, unknown> | null) {
    const detail = typeof body?.detail === 'string' ? body.detail : (typeof body?.title === 'string' ? body.title : `HTTP ${status}`)
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.code = typeof body?.code === 'string' ? body.code : 'http_error'
    this.detail = detail
    this.reason = typeof body?.reason === 'string' ? body.reason : undefined
    this.retryAfter = typeof body?.retry_after === 'number' ? body.retry_after : undefined
    this.errors = Array.isArray(body?.errors) ? (body.errors as FieldError[]) : []
    this.requestId = typeof body?.request_id === 'string' ? body.request_id : undefined
    this.field = typeof body?.field === 'string' ? body.field : undefined
    this.body = body ?? {}
  }

  /** The first message per body field: `{ password: 'Use at least 10 characters' }`. */
  fieldErrors (): Record<string, string> {
    const out: Record<string, string> = {}
    for (const e of this.errors) {
      const field = e.loc.at(0) === 'body' ? e.loc.at(1) : e.loc.at(-1)
      if (typeof field === 'string' && !(field in out)) {
        out[field] = e.msg
      }
    }
    return out
  }

  /** The `code` of the error on one body field, if any (`password_breached`, `wrong_password`). */
  fieldCode (field: string): string | undefined {
    return this.errors.find(e => e.loc.at(-1) === field)?.code
  }
}

/** The network itself failed (offline, DNS, TLS, connection reset). */
export class NetworkError extends Error {
  constructor (cause: unknown) {
    super('No connection', { cause })
    this.name = 'NetworkError'
  }
}

export async function toApiError (response: Response): Promise<ApiError> {
  let body: Record<string, unknown> | null = null
  try {
    body = await response.json() as Record<string, unknown>
  } catch {
    // Not JSON (an Nginx error page, an empty body): keep the status only
  }
  return new ApiError(response.status, body)
}
