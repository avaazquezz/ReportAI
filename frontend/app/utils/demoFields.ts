// How the landing's live demo shows what the pipeline extracted (GET /demo/reports/{id}): one row
// per field of the document type, in the schema's order, with the value written out as the report
// would print it. Pure, so tests/demoFields.test.ts checks it on its own.

export interface DemoFieldSpec {
  type: string
  label?: string | null
  required?: boolean
  /** A table's (list[object]) columns, in the template's order. */
  columns?: Record<string, DemoFieldSpec> | null
}

export interface DemoRow {
  key: string
  label: string
  value: string | null
  missing: boolean
}

/** The visitor's language and its words for a yes/no field. */
export interface DemoWriting {
  locale: string
  yes: string
  no: string
}

// What the report prints in an empty table cell (backend/app/services/i18n.py "none").
const NONE = '—'

const humanize = (key: string) => {
  const words = key.replace(/_/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

const blank = (value: unknown) =>
  value === null || value === undefined || (typeof value === 'string' && !value.trim()) || (Array.isArray(value) && value.length === 0)

// Dates, times and numbers follow backend/app/services/agent/summary.py format_value, the way the
// report itself writes them: 09/11/2026 and 2,5 in Spanish, 2026-11-09 and 2.5 in English.
function written(value: unknown, spec: DemoFieldSpec, how: DemoWriting): string | null {
  if (blank(value)) return null
  const spanish = how.locale === 'es'
  if (typeof value === 'boolean') return value ? how.yes : how.no
  if (typeof value === 'number') return spanish ? String(value).replace('.', ',') : String(value)
  if (spec.type === 'date' && typeof value === 'string' && spanish) {
    const date = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
    if (date) return `${date[3]}/${date[2]}/${date[1]}`
  }
  if (spec.type === 'time' && typeof value === 'string' && /^\d{2}:\d{2}/.test(value)) return value.slice(0, 5)
  if (Array.isArray(value)) {
    // A table prints one line per row with every column in the template's order, an empty one as
    // a dash, so a missing deadline shows; a list prints one item per line.
    const columns = Object.entries(spec.columns ?? {})
    const lines = value
      .map((item) => {
        if (!item || typeof item !== 'object') return written(item, { type: 'str' }, how)
        const row = item as Record<string, unknown>
        if (!columns.length) return Object.values(row).filter((cell) => !blank(cell)).map(String).join(' · ') || null
        const cells = columns.map(([name, column]) => written(row[name], column, how))
        return cells.some((cell) => cell !== null) ? cells.map((cell) => cell ?? NONE).join(' · ') : null
      })
      .filter((line): line is string => line !== null)
    return lines.length ? lines.join('\n') : null
  }
  return String(value)
}

/** The rows of the visitor's report. Photo fields are left out: the demo takes no photos. */
export function demoRows(
  schema: Record<string, DemoFieldSpec> | null,
  fields: Record<string, unknown> | null,
  missing: string[],
  how: DemoWriting
): DemoRow[] {
  if (!schema) return []
  return Object.entries(schema)
    .filter(([, spec]) => spec.type !== 'image')
    .map(([key, spec]) => ({
      key,
      label: spec.label?.trim() || humanize(key),
      value: written(fields?.[key], spec, how),
      missing: missing.includes(key)
    }))
}

/** Which limit a 429 from POST /demo/capture hit: this visitor's tries for the day ("You have used
 * your demo tries for today.") or the demo's cap for everyone ("The demo is full for today. Try
 * again tomorrow."), as backend/app/core/rate_limit.py words them. */
export function demoLimitHit(detail: unknown): 'perIp' | 'full' {
  return typeof detail === 'string' && /\bis full\b/i.test(detail) ? 'full' : 'perIp'
}
