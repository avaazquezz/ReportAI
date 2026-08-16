<script setup lang="ts">
import type { Report } from '~/types'

definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app' })

const { t } = useI18n()
const { formatDateTime } = useLocaleDate()
const { items, total, loading, error, fetchList, approve, reject, download } = useReports()
const { show } = useSnackbar()
const authStore = useAuthStore()
const isDemo = computed(() => authStore.user?.is_demo ?? false)

const STATUS_OPTIONS = computed(() => [
  { title: t('admin.reports.status.all'), value: null },
  { title: t('admin.reports.status.pending'), value: 'pending' },
  { title: t('admin.reports.status.awaitingApproval'), value: 'awaiting_approval' },
  { title: t('admin.reports.status.awaitingDoctypeSelection'), value: 'awaiting_doctype_selection' },
  { title: t('admin.reports.status.delivered'), value: 'delivered' },
  { title: t('admin.reports.status.failed'), value: 'failed' }
])

const STATUS_COLOR: Record<string, string> = {
  pending: 'pending',
  awaiting_approval: 'pending',
  awaiting_doctype_selection: 'pending',
  delivered: 'approved',
  failed: 'failed'
}

const STATUS_LABEL = computed<Record<string, string>>(() => ({
  pending: t('admin.reports.status.pending'),
  awaiting_approval: t('admin.reports.status.awaitingApproval'),
  awaiting_doctype_selection: t('admin.reports.status.awaitingDoctypeSelection'),
  delivered: t('admin.reports.status.delivered'),
  failed: t('admin.reports.status.failed')
}))

const AWAITING_STATUSES = ['awaiting_approval', 'awaiting_doctype_selection']

const statusFilter = ref<string | null>(null)
const lastOptions = ref({ page: 1, itemsPerPage: 10 })

const headers = computed(() => [
  { title: t('admin.reports.headers.documentType'), key: 'document_type_name' },
  { title: t('admin.channels.headers.channelType'), key: 'requester_channel' },
  { title: t('admin.common.statusLabel'), key: 'status' },
  { title: t('admin.common.createdLabel'), key: 'created_at' },
  { title: '', key: 'actions', sortable: false, width: '1%' }
])

const detailDialog = ref(false)
const selectedReport = ref<Report | null>(null)

function refetch(options: { page: number; itemsPerPage: number }) {
  lastOptions.value = options
  return fetchList({ ...options, status: statusFilter.value })
}

watch(statusFilter, () => refetch(lastOptions.value))

function openDetail(report: Report) {
  selectedReport.value = report
  detailDialog.value = true
}

async function onDownload(report: Report) {
  try {
    await download(report.id, `${report.document_type_name ?? 'report'}-${report.id}.pdf`)
  } catch {
    show(t('admin.reports.errors.download'), 'error')
  }
}

async function onApprove(report: Report) {
  try {
    await approve(report.id)
    show(t('admin.reports.toast.approved'), 'success')
  } catch {
    show(t('admin.reports.errors.approve'), 'error')
  }
  detailDialog.value = false
  await refetch(lastOptions.value)
}

async function onReject(report: Report) {
  try {
    await reject(report.id)
    show(t('admin.reports.toast.rejected'), 'success')
  } catch {
    show(t('admin.reports.errors.reject'), 'error')
  }
  detailDialog.value = false
  await refetch(lastOptions.value)
}
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="font-display text-2xl font-bold text-ink-900">{{ t('admin.layout.nav.reports') }}</h1>
      <v-select
        v-model="statusFilter"
        :items="STATUS_OPTIONS"
        item-title="title"
        item-value="value"
        :label="t('admin.common.statusLabel')"
        density="compact"
        hide-details
        style="max-width: 200px"
      />
    </div>

    <AdminResourceTable
      :headers="headers"
      :items="items"
      :total-items="total"
      :loading="loading"
      :error="error"
      @update:options="refetch"
    >
      <template #item.document_type_name="{ item }">
        {{ item.document_type_name ?? '—' }}
      </template>
      <template #item.status="{ item }">
        <v-chip :color="STATUS_COLOR[item.status] ?? 'default'" size="small" variant="tonal">
          {{ STATUS_LABEL[item.status] ?? item.status }}
        </v-chip>
      </template>
      <template #item.created_at="{ item }">
        {{ formatDateTime(item.created_at) }}
      </template>
      <template #item.actions="{ item }">
        <v-btn size="small" variant="text" @click="openDetail(item)">{{ t('admin.common.view') }}</v-btn>
      </template>
    </AdminResourceTable>

    <v-dialog v-model="detailDialog" max-width="480">
      <v-card v-if="selectedReport">
        <v-card-title>{{ t('admin.reports.dialog.title') }}</v-card-title>
        <v-card-text>
          <p class="mb-2 font-body text-sm text-ink-900/70">
            {{ t('admin.reports.dialog.type', { type: selectedReport.document_type_name ?? '—' }) }}
          </p>
          <p class="mb-2 font-body text-sm text-ink-900/70">
            {{ t('admin.reports.dialog.channel', { channel: selectedReport.requester_channel, identifier: selectedReport.requester_identifier }) }}
          </p>
          <v-chip :color="STATUS_COLOR[selectedReport.status] ?? 'default'" size="small" variant="tonal" class="mb-2">
            {{ STATUS_LABEL[selectedReport.status] ?? selectedReport.status }}
          </v-chip>
          <v-alert v-if="selectedReport.error_detail" type="error" variant="tonal" class="mt-2">
            {{ selectedReport.error_detail }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn
            v-if="!isDemo && selectedReport.status === 'awaiting_approval'"
            color="success"
            @click="onApprove(selectedReport)"
          >
            {{ t('admin.reports.actions.approve') }}
          </v-btn>
          <v-btn
            v-if="!isDemo && AWAITING_STATUSES.includes(selectedReport.status)"
            color="failed"
            variant="text"
            @click="onReject(selectedReport)"
          >
            {{ t('admin.reports.actions.reject') }}
          </v-btn>
          <v-btn v-if="selectedReport.download_url" color="primary" @click="onDownload(selectedReport)">
            {{ t('admin.reports.actions.downloadPdf') }}
          </v-btn>
          <v-btn variant="text" @click="detailDialog = false">{{ t('admin.common.close') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
