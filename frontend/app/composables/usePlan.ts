import type { PlanUsage } from '~/types'

export type PlanNotice = { type: 'info' | 'warning' | 'error'; key: string; params?: Record<string, number> }

const NEAR_QUOTA = 0.8

// The one place that reads what a company's plan says about right now: the banner on every
// page and the card on the usage page show the same thing.
export function planNotice(usage: PlanUsage | null, now = new Date()): PlanNotice | null {
  if (!usage) return null
  const end = usage.period_end ? new Date(usage.period_end) : null
  if (usage.status === 'canceled') return { type: 'error', key: 'admin.plan.notice.inactive' }
  if (usage.status === 'trialing' && end && end <= now) return { type: 'error', key: 'admin.plan.notice.trialEnded' }
  if (usage.reports_limit !== null && usage.reports_used >= usage.reports_limit) {
    return { type: 'error', key: 'admin.plan.notice.quotaReached', params: { limit: usage.reports_limit } }
  }
  if (usage.status === 'past_due') return { type: 'warning', key: 'admin.plan.notice.pastDue' }
  if (usage.reports_limit !== null && usage.reports_used >= usage.reports_limit * NEAR_QUOTA) {
    return { type: 'warning', key: 'admin.plan.notice.quotaNear', params: { used: usage.reports_used, limit: usage.reports_limit } }
  }
  if (usage.status === 'trialing' && end) {
    const days = Math.max(1, Math.ceil((end.getTime() - now.getTime()) / 86_400_000))
    return { type: 'info', key: 'admin.plan.notice.trialDaysLeft', params: { days } }
  }
  return null
}

export function usePlan() {
  const usage = useState<PlanUsage | null>('plan-usage', () => null)
  const notice = computed(() => planNotice(usage.value))

  async function load() {
    usage.value = await useApi()<PlanUsage>('/company/plan')
  }

  return { usage, notice, load }
}
