<script setup lang="ts">
// The company's plan for this period: which one, until when, and how much of it is used.
const { t } = useI18n()
const { formatDate } = useLocaleDate()
const { usage, notice, load } = usePlan()

const error = ref(false)
onMounted(async () => {
  try {
    await load()
  } catch {
    error.value = true
  }
})

const percent = computed(() => {
  const limit = usage.value?.reports_limit
  return limit ? Math.min(100, Math.round(((usage.value?.reports_used ?? 0) / limit) * 100)) : 0
})
</script>

<template>
  <v-alert v-if="error" type="error" variant="tonal">{{ t('admin.plan.errors.load') }}</v-alert>
  <v-card v-else-if="usage">
    <v-card-text>
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <p class="font-display text-lg font-bold text-ink-900">
          {{ t(`admin.plan.names.${usage.plan}`) }}
          <v-chip size="small" variant="tonal" class="ml-2">{{ t(`admin.plan.status.${usage.status}`) }}</v-chip>
        </p>
        <p v-if="usage.period_end" class="font-body text-sm text-ink-900/70">
          {{ t(usage.status === 'trialing' ? 'admin.plan.trialUntil' : 'admin.plan.renewsOn', { date: formatDate(usage.period_end) }) }}
        </p>
      </div>
      <template v-if="usage.reports_limit !== null">
        <p class="mt-4 font-body text-sm text-ink-900/70">
          {{ t('admin.plan.reportsUsed', { used: usage.reports_used, limit: usage.reports_limit }) }}
        </p>
        <v-progress-linear
          :model-value="percent"
          :color="notice?.type === 'error' ? 'error' : notice?.type === 'warning' ? 'warning' : 'primary'"
          height="8"
          rounded
          class="mt-2"
          :aria-label="t('admin.plan.reportsUsed', { used: usage.reports_used, limit: usage.reports_limit })"
        />
      </template>
      <p v-else class="mt-4 font-body text-sm text-ink-900/70">
        {{ t('admin.plan.noQuota', { used: usage.reports_used }) }}
      </p>
    </v-card-text>
  </v-card>
</template>
