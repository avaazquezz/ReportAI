import type { UpdateStatus } from '~/types'

// The layout and the dashboard both ask on the same page load: they share one request.
let inFlight: Promise<UpdateStatus | null> | null = null

/** This installation's release, the latest one and the advisories that affect it (once per visit). */
export function useUpdates() {
  const status = useState<UpdateStatus | null>('updateStatus', () => null)
  const loading = useState('updateStatusLoading', () => false)
  const api = useApi()

  async function fetchStatus(refresh: boolean) {
    loading.value = true
    try {
      status.value = await api<UpdateStatus>('/instance/version', { query: { refresh } })
    } catch {
      // Not knowing about updates is no reason to break the page; the settings page says so.
    } finally {
      loading.value = false
    }
    return status.value
  }

  function load(refresh = false): Promise<UpdateStatus | null> {
    if (status.value && !refresh) return Promise.resolve(status.value)
    if (!inFlight || refresh) inFlight = fetchStatus(refresh).finally(() => (inFlight = null))
    return inFlight
  }

  return { status, loading, load }
}
