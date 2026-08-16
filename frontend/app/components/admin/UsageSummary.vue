<script setup lang="ts">
const { t } = useI18n()
const props = withDefaults(defineProps<{ tenantId?: string }>(), { tenantId: undefined })

const { summary, loading, error, fetchSummary } = useUsageSummary(props.tenantId)

const STATUS_LABEL = computed<Record<string, string>>(() => ({
  pending: t('admin.reports.status.pending'),
  delivered: t('admin.reports.status.delivered'),
  failed: t('admin.reports.status.failed')
}))

const STATUS_COLOR: Record<string, string> = {
  pending: 'pending',
  delivered: 'approved',
  failed: 'failed'
}

const sparklineValues = computed(() => summary.value?.daily_cost.map((p) => p.cost_usd) ?? [])
const sparklineLabels = computed(
  () => summary.value?.daily_cost.map((p) => new Date(p.date).getDate().toString()) ?? []
)

onMounted(() => fetchSummary(30))
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
            v-if="sparklineValues.length"
            :model-value="sparklineValues"
            :labels="sparklineLabels"
            color="#FF6A45"
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
              :color="STATUS_COLOR[status] ?? 'default'"
              variant="tonal"
            >
              {{ STATUS_LABEL[status] ?? status }}: {{ count }}
            </v-chip>
          </template>
          <p v-else class="text-sm text-ink-900/60">{{ t('admin.usageSummary.noReports') }}</p>
        </v-card-text>
      </v-card>
    </template>
  </div>
</template>
