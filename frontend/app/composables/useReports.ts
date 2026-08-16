import type { PaginatedResponse, Report } from '~/types'

export function useReports() {
  const { t } = useI18n()
  const items = ref<Report[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchList(options: { page: number; itemsPerPage: number; status?: string | null }) {
    loading.value = true
    error.value = null
    try {
      const api = useApi()
      const skip = (options.page - 1) * options.itemsPerPage
      const query: Record<string, unknown> = { skip, limit: options.itemsPerPage }
      if (options.status) query.status = options.status
      const response = await api<PaginatedResponse<Report>>('/reports', { query })
      items.value = response.items
      total.value = response.total
    } catch {
      error.value = t('admin.reports.errors.list')
    } finally {
      loading.value = false
    }
  }

  async function getById(id: string): Promise<Report> {
    const api = useApi()
    return await api<Report>(`/reports/${id}`)
  }

  async function approve(id: string): Promise<Report> {
    const api = useApi()
    return await api<Report>(`/reports/${id}/approve`, { method: 'POST' })
  }

  async function reject(id: string): Promise<Report> {
    const api = useApi()
    return await api<Report>(`/reports/${id}/reject`, { method: 'POST' })
  }

  async function download(id: string, suggestedName: string) {
    const api = useApi()
    const blob = await api<Blob>(`/reports/${id}/download`, { responseType: 'blob' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = suggestedName
    link.click()
    URL.revokeObjectURL(url)
  }

  return { items, total, loading, error, fetchList, getById, approve, reject, download }
}
