<script setup lang="ts">
import type { ReportFilters } from '~/types'

definePageMeta({ middleware: ['auth', 'require-tenant-member'], layout: 'app', titleKey: 'admin.layout.nav.reports' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { formatDateTime } = useLocaleDate()
const { items, total, loading, error, fetchList, exportCsv } = useReports()
const { statusLabel, statusColor, statusOptions } = useReportStatus()
const { items: documentTypes, fetchList: fetchDocumentTypes } = useDocumentTypes()
const { show } = useSnackbar()

const REFRESH_EVERY_MS = 15_000
const CHANNELS = Object.entries(CHANNEL_NAMES).map(([value, title]) => ({ title, value }))

// The filters live in the URL, so coming back from a report finds the list as it was left.
function fromQuery(key: string): string | null {
  const value = route.query[key]
  return typeof value === 'string' && value ? value : null
}

const status = ref(fromQuery('status'))
const documentTypeId = ref(fromQuery('document_type_id'))
const channel = ref(fromQuery('channel'))
const dateFrom = ref(fromQuery('from'))
const dateTo = ref(fromQuery('to'))
const search = ref(fromQuery('q') ?? '')
const query = ref(search.value)

const page = ref(1)
const itemsPerPage = ref(10)

const filters = computed<ReportFilters>(() => ({
  status: status.value,
  document_type_id: documentTypeId.value,
  channel: channel.value,
  created_from: dateFrom.value ? parseLocalDay(dateFrom.value).toISOString() : null,
  // Inclusive for the person picking it: everything before the next day starts.
  created_to: dateTo.value ? parseLocalDay(dateTo.value, 1).toISOString() : null,
  q: query.value.trim() || null
}))

const hasFilters = computed(() =>
  Boolean(status.value || documentTypeId.value || channel.value || dateFrom.value || dateTo.value || query.value)
)

const headers = computed(() => [
  { title: t('admin.reports.headers.documentType'), key: 'document_type_name' },
  { title: t('admin.reports.headers.requester'), key: 'requester_name' },
  { title: t('admin.channels.headers.channelType'), key: 'requester_channel' },
  { title: t('admin.common.statusLabel'), key: 'status' },
  { title: t('admin.common.createdLabel'), key: 'created_at' },
  { title: '', key: 'actions', width: '1%' }
])

function load(options = { page: page.value, itemsPerPage: itemsPerPage.value }, quiet = false) {
  page.value = options.page
  itemsPerPage.value = options.itemsPerPage
  return fetchList({ ...options, filters: filters.value, quiet })
}

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, (value) => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => (query.value = value), 300)
})

watch(filters, () => {
  router.replace({
    query: Object.fromEntries(
      Object.entries({
        status: status.value,
        document_type_id: documentTypeId.value,
        channel: channel.value,
        from: dateFrom.value,
        to: dateTo.value,
        q: query.value.trim()
      }).filter(([, value]) => value)
    )
  })
  if (page.value === 1) load()
  else page.value = 1 // the table asks for page 1 itself
})

function clearFilters() {
  status.value = documentTypeId.value = channel.value = dateFrom.value = dateTo.value = null
  search.value = query.value = ''
}

async function onExport() {
  try {
    await exportCsv(filters.value)
  } catch {
    show(t('admin.reports.errors.export'), 'error')
  }
}

// Reports move on their own (the worker finishes them, people answer): keep the list current
// while it is on screen, without the loading flash.
let refreshTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  fetchDocumentTypes({ page: 1, itemsPerPage: 100 })
  refreshTimer = setInterval(() => {
    if (document.visibilityState === 'visible' && !loading.value) load(undefined, true)
  }, REFRESH_EVERY_MS)
})
onBeforeUnmount(() => {
  clearInterval(refreshTimer)
  clearTimeout(searchTimer)
})
</script>

<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h1 class="font-display text-2xl font-bold text-ink-900">{{ t('admin.layout.nav.reports') }}</h1>
      <v-btn variant="tonal" prepend-icon="mdi-file-delimited-outline" @click="onExport">
        {{ t('admin.reports.filters.exportCsv') }}
      </v-btn>
    </div>

    <v-card class="mb-4" flat border>
      <v-card-text class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-12">
        <v-text-field
          v-model="search"
          :label="t('admin.reports.filters.search')"
          prepend-inner-icon="mdi-magnify"
          density="compact"
          hide-details
          clearable
          class="lg:col-span-3"
          @click:clear="search = ''"
        />
        <v-select
          v-model="status"
          :items="statusOptions"
          :label="t('admin.common.statusLabel')"
          density="compact"
          hide-details
          clearable
          class="lg:col-span-2"
        />
        <v-select
          v-model="documentTypeId"
          :items="documentTypes"
          item-title="name"
          item-value="id"
          :label="t('admin.reports.headers.documentType')"
          density="compact"
          hide-details
          clearable
          class="lg:col-span-2"
        />
        <v-select
          v-model="channel"
          :items="CHANNELS"
          :label="t('admin.channels.headers.channelType')"
          density="compact"
          hide-details
          clearable
          class="lg:col-span-2"
        />
        <div class="flex gap-2 sm:col-span-2 lg:col-span-3">
          <v-text-field v-model="dateFrom" type="date" :label="t('admin.reports.filters.from')" density="compact" hide-details />
          <v-text-field v-model="dateTo" type="date" :label="t('admin.reports.filters.to')" density="compact" hide-details />
        </div>
      </v-card-text>
      <v-card-actions v-if="hasFilters" class="pt-0">
        <v-btn size="small" variant="text" @click="clearFilters">{{ t('admin.reports.filters.clear') }}</v-btn>
      </v-card-actions>
    </v-card>

    <AdminResourceTable
      v-model:page="page"
      :headers="headers"
      :items="items"
      :total-items="total"
      :loading="loading"
      :error="error"
      @update:options="load"
    >
      <template #item.document_type_name="{ item }">
        <NuxtLink :to="`/admin/reports/${item.id}`" class="font-medium text-ink-900 underline-offset-2 hover:underline">
          {{ item.document_type_name ?? t('admin.reports.noType') }}
        </NuxtLink>
      </template>
      <template #item.requester_name="{ item }">{{ item.requester_name ?? item.requester_identifier }}</template>
      <template #item.requester_channel="{ item }">{{ channelName(item.requester_channel) }}</template>
      <template #item.status="{ item }">
        <v-chip :color="statusColor(item.status)" size="small" variant="tonal">
          {{ statusLabel(item.status) }}
        </v-chip>
      </template>
      <template #item.created_at="{ item }">
        {{ formatDateTime(item.created_at) }}
      </template>
      <template #item.actions="{ item }">
        <v-btn size="small" variant="text" :to="`/admin/reports/${item.id}`">{{ t('admin.common.view') }}</v-btn>
      </template>
    </AdminResourceTable>
  </div>
</template>
