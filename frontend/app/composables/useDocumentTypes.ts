import type {
  DocumentTemplate,
  DocumentType,
  DocumentTypeWriteRequest,
  PaginatedResponse
} from '~/types'

export function useDocumentTypes() {
  const items = ref<DocumentType[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchList(options: { page: number; itemsPerPage: number }) {
    loading.value = true
    error.value = null
    try {
      const api = useApi()
      const skip = (options.page - 1) * options.itemsPerPage
      const response = await api<PaginatedResponse<DocumentType>>('/document-types', {
        query: { skip, limit: options.itemsPerPage }
      })
      items.value = response.items
      total.value = response.total
    } catch {
      error.value = 'No se pudieron cargar los tipos de documento.'
    } finally {
      loading.value = false
    }
  }

  async function create(payload: DocumentTypeWriteRequest): Promise<DocumentType> {
    const api = useApi()
    return await api<DocumentType>('/document-types', { method: 'POST', body: payload })
  }

  async function update(id: string, payload: DocumentTypeWriteRequest): Promise<DocumentType> {
    const api = useApi()
    return await api<DocumentType>(`/document-types/${id}`, { method: 'PATCH', body: payload })
  }

  async function getById(id: string): Promise<DocumentType> {
    const api = useApi()
    return await api<DocumentType>(`/document-types/${id}`)
  }

  async function listTemplates(documentTypeId: string): Promise<DocumentTemplate[]> {
    const api = useApi()
    const response = await api<PaginatedResponse<DocumentTemplate>>(
      `/document-types/${documentTypeId}/templates`,
      { query: { limit: 50 } }
    )
    return response.items
  }

  async function uploadTemplate(documentTypeId: string, file: File): Promise<DocumentTemplate> {
    const api = useApi()
    const formData = new FormData()
    formData.append('file', file)
    return await api<DocumentTemplate>(`/document-types/${documentTypeId}/templates`, {
      method: 'POST',
      body: formData
    })
  }

  return { items, total, loading, error, fetchList, create, update, getById, listTemplates, uploadTemplate }
}
