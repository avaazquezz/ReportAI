// The one place that knows every report status: the history, the detail page and the usage
// summary used to keep their own, incomplete copies (FE-11).
export const REPORT_STATUSES = [
  'pending',
  'awaiting_doctype_selection',
  'awaiting_details',
  'awaiting_approval',
  'delivered',
  'delivery_failed',
  'failed',
  'cancelled'
] as const

// Waiting on a person: these can be rejected from the panel.
export const PAUSED_STATUSES = ['awaiting_doctype_selection', 'awaiting_details', 'awaiting_approval']
// The PDF exists, whether or not its copies arrived: it can be edited and sent again.
export const FINISHED_STATUSES = ['delivered', 'delivery_failed']

const COLORS: Record<string, string> = {
  pending: 'pending',
  awaiting_doctype_selection: 'pending',
  awaiting_details: 'pending',
  awaiting_approval: 'pending',
  delivered: 'approved',
  delivery_failed: 'failed',
  failed: 'failed',
  cancelled: 'default'
}

export function useReportStatus() {
  const { t, te } = useI18n()

  function statusLabel(status: string): string {
    const key = `admin.reports.status.${status}`
    return te(key) ? t(key) : status
  }

  function statusColor(status: string): string {
    return COLORS[status] ?? 'default'
  }

  const statusOptions = computed(() => REPORT_STATUSES.map((value) => ({ title: statusLabel(value), value })))

  return { statusLabel, statusColor, statusOptions }
}
