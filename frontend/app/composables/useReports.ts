import type { PaginatedResponse, Report, ReportDetail, ReportFilters } from '~/types'

function compact(filters: ReportFilters): Record<string, string> {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value)) as Record<string, string>
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function useReports() {
  const { t } = useI18n()
  const api = useApi()
  const items = ref<Report[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchList(options: { page: number; itemsPerPage: number; filters?: ReportFilters; quiet?: boolean }) {
    // A background refresh keeps the table as it is instead of flashing the loading state.
    if (!options.quiet) loading.value = true
    error.value = null
    try {
      const skip = (options.page - 1) * options.itemsPerPage
      const response = await api<PaginatedResponse<Report>>('/reports', {
        query: { skip, limit: options.itemsPerPage, ...compact(options.filters ?? {}) }
      })
      items.value = response.items
      total.value = response.total
    } catch {
      error.value = t('admin.reports.errors.list')
    } finally {
      loading.value = false
    }
  }

  async function exportCsv(filters: ReportFilters) {
    const blob = await api<Blob>('/reports/export.csv', { query: compact(filters), responseType: 'blob' })
    saveBlob(blob, 'reports.csv')
  }

  const getById = (id: string) => api<ReportDetail>(`/reports/${id}`)

  const approve = (id: string, fields: Record<string, unknown>) =>
    api<ReportDetail>(`/reports/${id}/approve`, { method: 'POST', body: { fields } })

  const reject = (id: string, reason: string | null) =>
    api<ReportDetail>(`/reports/${id}/reject`, { method: 'POST', body: { reason } })

  const retry = (id: string) => api<ReportDetail>(`/reports/${id}/retry`, { method: 'POST' })

  const editFields = (id: string, fields: Record<string, unknown>) =>
    api<ReportDetail>(`/reports/${id}/fields`, { method: 'PATCH', body: { fields } })

  const preview = (id: string, fields: Record<string, unknown>) =>
    api<Blob>(`/reports/${id}/preview`, { method: 'POST', body: { fields }, responseType: 'blob' })

  const resend = (id: string, target: { delivery_id?: string; email?: string } = {}) =>
    api<ReportDetail>(`/reports/${id}/resend`, { method: 'POST', body: target })

  // Audio, photos and the PDF need the bearer token, so they are fetched, not linked.
  const fetchBlob = (url: string) => api<Blob>(url, { responseType: 'blob' })

  return { items, total, loading, error, fetchList, exportCsv, getById, approve, reject, retry, editFields, preview, resend, fetchBlob }
}
