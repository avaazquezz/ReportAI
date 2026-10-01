<script setup lang="ts">
const { t } = useI18n()
const { status, loading, load } = useUpdates()
const { formatDateTime } = useLocaleDate()

onMounted(() => load(true))
</script>

<template>
  <div>
    <v-progress-linear v-if="loading && !status" indeterminate color="primary" />
    <template v-else-if="status">
      <dl class="grid max-w-md grid-cols-2 gap-y-2 text-sm">
        <dt class="text-ink-900/70">{{ t('admin.updates.current') }}</dt>
        <dd class="font-semibold">{{ status.current }}</dd>
        <dt class="text-ink-900/70">{{ t('admin.updates.latest') }}</dt>
        <dd class="font-semibold">
          <a v-if="status.latest_url" :href="status.latest_url" target="_blank" rel="noopener" class="underline">{{ status.latest }}</a>
          <span v-else>{{ status.latest ?? '—' }}</span>
        </dd>
        <template v-if="status.checked_at">
          <dt class="text-ink-900/70">{{ t('admin.updates.checked') }}</dt>
          <dd>{{ formatDateTime(status.checked_at) }}</dd>
        </template>
      </dl>

      <v-alert v-if="status.error" class="mt-4" type="warning" variant="tonal">{{ status.error }}</v-alert>
      <v-alert v-for="advisory in status.advisories" :key="advisory.id" class="mt-4" type="error" variant="tonal" :title="advisory.title">
        {{ t('admin.updates.advisory', { id: advisory.id, severity: advisory.severity, fixed: advisory.fixed_in }) }}
        <a v-if="advisory.url" :href="advisory.url" target="_blank" rel="noopener" class="ml-1 underline">{{ t('admin.updates.details') }}</a>
      </v-alert>
      <v-alert v-if="status.update_available" class="mt-4" type="info" variant="tonal">
        {{ t('admin.updates.available', { version: status.latest }) }}
      </v-alert>
      <v-alert v-else-if="!status.error && status.latest" class="mt-4" type="success" variant="tonal">{{ t('admin.updates.upToDate') }}</v-alert>

      <h3 class="mt-6 font-display text-lg font-bold">{{ t('admin.updates.howTitle') }}</h3>
      <p class="mt-1 text-sm text-ink-900/70">{{ t('admin.updates.howHelp') }}</p>
      <pre class="mt-2 rounded bg-paper-100 px-3 py-2 text-sm">reportai update</pre>
      <v-btn class="mt-4" variant="tonal" :loading="loading" @click="load(true)">{{ t('admin.updates.checkNow') }}</v-btn>
    </template>
  </div>
</template>
