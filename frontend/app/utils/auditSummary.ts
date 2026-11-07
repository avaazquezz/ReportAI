// One line out of an audit event's details, for the audit log table (tests/auditSummary.test.ts).
// The keys are the backend's own field names: technical, but exact, which is what an audit is for.

function isChange(value: unknown): value is { from: unknown; to: unknown } {
  return typeof value === 'object' && value !== null && 'from' in value && 'to' in value
}

function show(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ')
  if (isChange(value)) return `${show(value.from)} → ${show(value.to)}`
  if (typeof value === 'object' && value !== null) return auditSummary(value as Record<string, unknown>)
  return String(value)
}

export function auditSummary(details: Record<string, unknown> | null): string {
  if (!details) return ''
  return Object.entries(details)
    // "changes" and "fields" only wrap what changed: their name adds nothing to the line.
    .map(([key, value]) => (key === 'changes' || key === 'fields' ? show(value) : `${key}: ${show(value)}`))
    .join(' · ')
}
