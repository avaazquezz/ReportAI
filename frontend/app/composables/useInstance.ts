import type { SetupStatus } from '~/types'

/**
 * Whether this installation serves one company (and so whether its admin also runs the
 * installation's settings), and whether it still has to be set up. Asked once per visit.
 */
export function useInstance() {
  const status = useState<SetupStatus | null>('setupStatus', () => null)

  async function load(): Promise<SetupStatus | null> {
    if (status.value) return status.value
    try {
      status.value = await useApi()<SetupStatus>('/setup/status')
    } catch {
      // The API being down must not make every page unreachable; pages report their own errors.
      return null
    }
    return status.value
  }

  function markSetUp() {
    if (status.value) status.value = { ...status.value, needs_setup: false }
  }

  return { status, load, markSetUp }
}

const TENANT_ROLES = ['tenant_admin', 'approver', 'viewer']

/** What the signed-in person may do: mirrors the API's require_* dependencies. */
export function useRole() {
  const authStore = useAuthStore()
  const { status } = useInstance()
  const role = computed(() => authStore.user?.role ?? '')
  const isAdmin = computed(() => role.value === 'tenant_admin')
  const isSuperAdmin = computed(() => role.value === 'super_admin')
  const isMember = computed(() => TENANT_ROLES.includes(role.value))
  const canApprove = computed(() => role.value === 'tenant_admin' || role.value === 'approver')
  // Runs the installation (AI keys, email server, updates): its company's admin when it serves one
  // company, the super admin when it hosts several.
  const isInstanceAdmin = computed(() =>
    status.value?.single_tenant ? role.value === 'tenant_admin' : role.value === 'super_admin'
  )
  return { role, isAdmin, isSuperAdmin, isMember, canApprove, isInstanceAdmin }
}
