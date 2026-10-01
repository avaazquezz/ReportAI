import type { CheckResult } from '~/types'

/** A "Test" call that failed. One the API refused as incomplete (422, e.g. no key typed) is said in
 * the reader's language, not with the API's English message. */
export function failedCheck(err: unknown, fallback: string): CheckResult {
  const error = err as { statusCode?: number; status?: number; data?: { detail?: unknown } }
  if ((error?.statusCode ?? error?.status) === 422) return { ok: false, reason: 'not_configured', detail: null }
  const detail = error?.data?.detail
  return { ok: false, reason: null, detail: typeof detail === 'string' ? detail : fallback }
}
