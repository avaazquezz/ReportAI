<script setup lang="ts">
import type { AuditEvent, PaginatedResponse } from '~/types'

definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app', titleKey: 'admin.layout.nav.audit' })

const { t, te } = useI18n()
const api = useApi()
const { formatDateTime } = useLocaleDate()

const items = ref<AuditEvent[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

async function fetchList(options: { page: number; itemsPerPage: number }) {
  loading.value = true
  error.value = null
  try {
    const response = await api<PaginatedResponse<AuditEvent>>('/audit', {
      query: { skip: (options.page - 1) * options.itemsPerPage, limit: options.itemsPerPage }
    })
    items.value = response.items
    total.value = response.total
  } catch {
    error.value = t('admin.audit.errors.load')
  } finally {
    loading.value = false
  }
}
const { page, load } = useTablePaging(fetchList)

const headers = computed(() => [
  { title: t('admin.audit.headers.when'), key: 'created_at', width: '1%' },
  { title: t('admin.audit.headers.who'), key: 'actor_label' },
  { title: t('admin.audit.headers.what'), key: 'action' },
  { title: t('admin.audit.headers.details'), key: 'details' }
])

// An action this panel has no words for yet (a newer backend) still shows, as its key.
function actionLabel(action: string) {
  const key = `admin.audit.actions.${action}`
  return te(key) ? t(key) : action
}

function actorLabel(event: AuditEvent) {
  if (event.actor_label === 'system') return t('admin.audit.system')
  return event.actor_label ?? t('admin.audit.anonymous')
}
</script>

<template>
  <div>
    <h1 class="mb-2 font-display text-2xl font-bold text-ink-900">{{ t('admin.layout.nav.audit') }}</h1>
    <p class="mb-6 text-ink-900/70">{{ t('admin.audit.help') }}</p>

    <AdminResourceTable
      v-model:page="page"
      :headers="headers"
      :items="items"
      :total-items="total"
      :loading="loading"
      :error="error"
      @update:options="load"
    >
      <template #item.created_at="{ item }">
        <span class="whitespace-nowrap">{{ formatDateTime(item.created_at) }}</span>
      </template>
      <template #item.actor_label="{ item }">
        {{ actorLabel(item) }}
        <span v-if="item.ip" class="block text-xs text-ink-900/70">{{ item.ip }}</span>
      </template>
      <template #item.action="{ item }">{{ actionLabel(item.action) }}</template>
      <template #item.details="{ item }">
        <span class="text-sm text-ink-900/80">{{ auditSummary(item.details) || item.target }}</span>
      </template>
    </AdminResourceTable>
  </div>
</template>
