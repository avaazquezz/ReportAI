<script setup lang="ts">
import type { Report } from '~/types'

definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app' })

const { items, total, loading, error, fetchList, approve, reject, download } = useReports()
const { show } = useSnackbar()
const authStore = useAuthStore()
const isDemo = computed(() => authStore.user?.is_demo ?? false)

const STATUS_OPTIONS = [
  { title: 'Todos', value: null },
  { title: 'Pendiente', value: 'pending' },
  { title: 'Esperando aprobación', value: 'awaiting_approval' },
  { title: 'Esperando selección', value: 'awaiting_doctype_selection' },
  { title: 'Entregado', value: 'delivered' },
  { title: 'Fallido', value: 'failed' }
]

const STATUS_COLOR: Record<string, string> = {
  pending: 'pending',
  awaiting_approval: 'pending',
  awaiting_doctype_selection: 'pending',
  delivered: 'approved',
  failed: 'failed'
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'Pendiente',
  awaiting_approval: 'Esperando aprobación',
  awaiting_doctype_selection: 'Esperando selección',
  delivered: 'Entregado',
  failed: 'Fallido'
}

const AWAITING_STATUSES = ['awaiting_approval', 'awaiting_doctype_selection']

const statusFilter = ref<string | null>(null)
const lastOptions = ref({ page: 1, itemsPerPage: 10 })

const headers = [
  { title: 'Tipo de documento', key: 'document_type_name' },
  { title: 'Canal', key: 'requester_channel' },
  { title: 'Estado', key: 'status' },
  { title: 'Creado', key: 'created_at' },
  { title: '', key: 'actions', sortable: false, width: '1%' }
]

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
    show('No se pudo descargar el informe.', 'error')
  }
}

async function onApprove(report: Report) {
  try {
    await approve(report.id)
    show('Informe aprobado — generando el documento.', 'success')
  } catch {
    show('No se pudo aprobar el informe.', 'error')
  }
  detailDialog.value = false
  await refetch(lastOptions.value)
}

async function onReject(report: Report) {
  try {
    await reject(report.id)
    show('Informe rechazado.', 'success')
  } catch {
    show('No se pudo rechazar el informe.', 'error')
  }
  detailDialog.value = false
  await refetch(lastOptions.value)
}
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="font-display text-2xl font-bold text-ink-900">Informes</h1>
      <v-select
        v-model="statusFilter"
        :items="STATUS_OPTIONS"
        item-title="title"
        item-value="value"
        label="Estado"
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
        {{ new Date(item.created_at).toLocaleString('es-ES') }}
      </template>
      <template #item.actions="{ item }">
        <v-btn size="small" variant="text" @click="openDetail(item)">Ver</v-btn>
      </template>
    </AdminResourceTable>

    <v-dialog v-model="detailDialog" max-width="480">
      <v-card v-if="selectedReport">
        <v-card-title>Informe</v-card-title>
        <v-card-text>
          <p class="mb-2 font-body text-sm text-ink-900/70">
            Tipo: {{ selectedReport.document_type_name ?? '—' }}
          </p>
          <p class="mb-2 font-body text-sm text-ink-900/70">
            Canal: {{ selectedReport.requester_channel }} ({{ selectedReport.requester_identifier }})
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
            Aprobar
          </v-btn>
          <v-btn
            v-if="!isDemo && AWAITING_STATUSES.includes(selectedReport.status)"
            color="failed"
            variant="text"
            @click="onReject(selectedReport)"
          >
            Rechazar
          </v-btn>
          <v-btn v-if="selectedReport.download_url" color="primary" @click="onDownload(selectedReport)">
            Descargar PDF
          </v-btn>
          <v-btn variant="text" @click="detailDialog = false">Cerrar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
