import type { PaginatedResponse, PlanKey, PlanStatus, Tenant, TenantCreateRequest, TenantCreateResponse } from '~/types'

export function useTenants() {
  const { t } = useI18n()
  const items = ref<Tenant[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchList(options: { page: number; itemsPerPage: number }) {
    loading.value = true
    error.value = null
    try {
      const api = useApi()
      const skip = (options.page - 1) * options.itemsPerPage
      const response = await api<PaginatedResponse<Tenant>>('/admin/tenants', {
        query: { skip, limit: options.itemsPerPage }
      })
      items.value = response.items
      total.value = response.total
    } catch {
      error.value = t('admin.tenants.errors.list')
    } finally {
      loading.value = false
    }
  }

  async function create(payload: TenantCreateRequest): Promise<TenantCreateResponse> {
    const api = useApi()
    return await api<TenantCreateResponse>('/admin/tenants', { method: 'POST', body: payload })
  }

  async function setActive(id: string, isActive: boolean) {
    const api = useApi()
    await api(`/admin/tenants/${id}`, { method: 'PATCH', body: { is_active: isActive } })
  }

  // A new plan starts a new period from now; a status on its own keeps the period.
  async function setPlan(id: string, change: { plan?: PlanKey; plan_status?: PlanStatus }): Promise<Tenant> {
    const api = useApi()
    return await api<Tenant>(`/admin/tenants/${id}`, { method: 'PATCH', body: change })
  }

  async function resendInvite(id: string) {
    const api = useApi()
    return await api<{ message: string }>(`/admin/tenants/${id}/resend-invite`, { method: 'POST' })
  }

  async function getById(id: string): Promise<Tenant> {
    const api = useApi()
    return await api<Tenant>(`/admin/tenants/${id}`)
  }

  return { items, total, loading, error, fetchList, create, setActive, setPlan, resendInvite, getById }
}
