import type { UsageSummary } from '~/types'

export function useUsageSummary(tenantId?: string) {
  const { t } = useI18n()
  const summary = ref<UsageSummary | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchSummary(days = 30) {
    loading.value = true
    error.value = null
    try {
      const api = useApi()
      const path = tenantId ? `/admin/tenants/${tenantId}/usage/summary` : '/usage/summary'
      summary.value = await api<UsageSummary>(path, { query: { days } })
    } catch {
      error.value = t('admin.usageSummary.errors.load')
    } finally {
      loading.value = false
    }
  }

  return { summary, loading, error, fetchSummary }
}
