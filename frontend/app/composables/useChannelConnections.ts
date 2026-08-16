import type {
  ChannelConnection,
  ChannelConnectionCreateRequest,
  ChannelConnectionUpdateRequest,
  PaginatedResponse
} from '~/types'

export function useChannelConnections() {
  const { t } = useI18n()
  const items = ref<ChannelConnection[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchList(options: { page: number; itemsPerPage: number }) {
    loading.value = true
    error.value = null
    try {
      const api = useApi()
      const skip = (options.page - 1) * options.itemsPerPage
      const response = await api<PaginatedResponse<ChannelConnection>>('/channels', {
        query: { skip, limit: options.itemsPerPage }
      })
      items.value = response.items
      total.value = response.total
    } catch {
      error.value = t('admin.channels.errors.list')
    } finally {
      loading.value = false
    }
  }

  async function create(payload: ChannelConnectionCreateRequest): Promise<ChannelConnection> {
    const api = useApi()
    return await api<ChannelConnection>('/channels', { method: 'POST', body: payload })
  }

  async function update(
    id: string,
    payload: ChannelConnectionUpdateRequest
  ): Promise<ChannelConnection> {
    const api = useApi()
    return await api<ChannelConnection>(`/channels/${id}`, { method: 'PATCH', body: payload })
  }

  return { items, total, loading, error, fetchList, create, update }
}
