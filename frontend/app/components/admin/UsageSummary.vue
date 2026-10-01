<script setup lang="ts">
const { t } = useI18n()
const props = withDefaults(defineProps<{ tenantId?: string }>(), { tenantId: undefined })

const DAYS = 30
const { summary, loading, error, fetchSummary } = useUsageSummary(props.tenantId)
const { statusLabel, statusColor } = useReportStatus()

function dayKey(day: Date) {
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
}

// Every day of the period, quiet ones at zero: the API only returns days with activity, and a line
// joining 3 Sep straight to 20 Sep drew a trend that never happened (FE-9).
const dailySeries = computed(() => {
  const costs = new Map((summary.value?.daily_cost ?? []).map((point) => [point.date, point.cost_usd]))
  const today = new Date()
  return Array.from({ length: DAYS }, (_, index) => {
    const day = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (DAYS - 1 - index))
    return { label: String(day.getDate()), cost: costs.get(dayKey(day)) ?? 0 }
  })
})

const sparklineValues = computed(() => dailySeries.value.map((point) => point.cost))
const sparklineLabels = computed(() => dailySeries.value.map((point, index) => (index % 5 === 4 ? point.label : ' ')))
const hasActivity = computed(() => sparklineValues.value.some((cost) => cost > 0))

onMounted(() => fetchSummary(DAYS))
</script>

<template>
  <div>
    <v-alert v-if="error" type="error" variant="tonal">{{ error }}</v-alert>
    <v-skeleton-loader v-else-if="loading" type="card" />

    <template v-else-if="summary">
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <v-card>
          <v-card-text>
            <p class="font-body text-sm text-ink-900/60">{{ t('admin.usageSummary.costLabel') }}</p>
            <p class="font-display text-2xl font-bold text-ink-900">
              ${{ summary.total_cost_usd.toFixed(2) }}
            </p>
          </v-card-text>
        </v-card>
        <v-card>
          <v-card-text>
            <p class="font-body text-sm text-ink-900/60">{{ t('admin.usageSummary.reportsGeneratedLabel') }}</p>
            <p class="font-display text-2xl font-bold text-ink-900">{{ summary.total_reports }}</p>
          </v-card-text>
        </v-card>
        <v-card>
          <v-card-text>
            <p class="font-body text-sm text-ink-900/60">{{ t('admin.usageSummary.avgLatencyLabel') }}</p>
            <p class="font-display text-2xl font-bold text-ink-900">
              {{ summary.avg_latency_ms ? Math.round(summary.avg_latency_ms) + ' ms' : '—' }}
            </p>
          </v-card-text>
        </v-card>
      </div>

      <v-card class="mt-4">
        <v-card-title>{{ t('admin.usageSummary.dailyCostTitle') }}</v-card-title>
        <v-card-text>
          <v-sparkline
            v-if="hasActivity"
            :model-value="sparklineValues"
            :labels="sparklineLabels"
            color="#C0432A"
            line-width="2"
            padding="8"
            smooth
          />
          <p v-else class="py-6 text-center text-sm text-ink-900/60">{{ t('admin.usageSummary.noActivity') }}</p>
        </v-card-text>
      </v-card>

      <v-card class="mt-4">
        <v-card-title>{{ t('admin.usageSummary.byStatusTitle') }}</v-card-title>
        <v-card-text class="flex flex-wrap gap-2">
          <template v-if="Object.keys(summary.reports_by_status).length">
            <v-chip
              v-for="(count, status) in summary.reports_by_status"
              :key="status"
              :color="statusColor(String(status))"
              variant="tonal"
            >
              {{ statusLabel(String(status)) }}: {{ count }}
            </v-chip>
          </template>
          <p v-else class="text-sm text-ink-900/60">{{ t('admin.usageSummary.noReports') }}</p>
        </v-card-text>
      </v-card>
    </template>
  </div>
</template>
