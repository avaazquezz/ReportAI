<script setup lang="ts">
import type { Dashboard } from '~/types'

definePageMeta({ middleware: 'auth', layout: 'app', titleKey: 'admin.dashboard.title' })

const { t } = useI18n()
const authStore = useAuthStore()
const api = useApi()
const { isMember, isInstanceAdmin } = useRole()
const { statusLabel, statusColor } = useReportStatus()
const { formatDateTime } = useLocaleDate()
const { status: updates, load: loadUpdates } = useUpdates()

const board = ref<Dashboard | null>(null)
const loadError = ref('')

onMounted(async () => {
  if (isInstanceAdmin.value) loadUpdates()
  if (!isMember.value) return // a super admin has no company of their own to show
  try {
    board.value = await api<Dashboard>('/dashboard')
  } catch {
    loadError.value = t('admin.dashboard.errors.load')
  }
})

// What is left before the first report, each with where to do it. The first three are the
// installation's settings: a company admin who doesn't run the installation can only read them.
const steps = computed(() => {
  const done = board.value?.checklist
  if (!done) return []
  const settings = isInstanceAdmin.value ? '/admin/settings' : null
  return [
    { key: 'ai', done: done.ai, to: settings && `${settings}?tab=ai` },
    { key: 'transcription', done: done.transcription, to: settings && `${settings}?tab=ai`, optional: true },
    { key: 'email', done: done.email, to: settings && `${settings}?tab=email`, optional: true },
    { key: 'document_type', done: done.document_type, to: '/admin/document-types' },
    { key: 'channel', done: done.channel, to: '/admin/channels' },
    { key: 'senders', done: done.senders, to: '/admin/channels' },
    { key: 'first_report', done: done.first_report, to: null }
  ]
})
const pendingSteps = computed(() => steps.value.filter((s) => !s.done && !s.optional).length)

const counts = computed(() =>
  board.value
    ? [
        { key: 'waiting', value: board.value.counts.waiting, color: 'pending' },
        { key: 'processing', value: board.value.counts.processing, color: 'default' },
        { key: 'delivered', value: board.value.counts.delivered_recently, color: 'approved' },
        { key: 'failed', value: board.value.counts.failed_recently, color: 'failed' },
        { key: 'failedCopies', value: board.value.counts.failed_copies_recently, color: 'failed' }
      ]
    : []
)
</script>

<template>
  <div>
    <h1 class="font-display text-2xl font-bold text-ink-900">
      {{ t('admin.dashboard.greeting', { name: authStore.user?.full_name }) }}
    </h1>

    <v-alert
      v-if="isInstanceAdmin && updates?.update_available && !updates.advisories.length"
      class="mt-6"
      type="info"
      variant="tonal"
      :text="t('admin.updates.available', { version: updates.latest })"
    >
      <template #append>
        <v-btn variant="text" to="/admin/settings?tab=updates">{{ t('admin.updates.howTo') }}</v-btn>
      </template>
    </v-alert>

    <v-alert v-if="loadError" class="mt-6" type="error" variant="tonal">{{ loadError }}</v-alert>

    <p v-if="!isMember" class="mt-6 text-ink-900/70">{{ t('admin.dashboard.hint') }}</p>

    <template v-if="board">
      <v-card v-if="steps.length && pendingSteps" class="mt-6 pa-6" rounded="lg" elevation="0" border>
        <h2 class="font-display text-lg font-bold">{{ t('admin.dashboard.checklist.title') }}</h2>
        <p class="mb-4 text-sm text-ink-900/70">{{ t('admin.dashboard.checklist.help', { n: pendingSteps }) }}</p>
        <ul class="space-y-2">
          <li v-for="step in steps" :key="step.key" class="flex items-start gap-3">
            <v-icon
              :icon="step.done ? 'mdi-check-circle' : 'mdi-checkbox-blank-circle-outline'"
              :color="step.done ? 'success' : undefined"
              size="20"
              class="mt-0.5"
            />
            <div class="flex-1">
              <span :class="step.done ? 'text-ink-900/60 line-through' : 'font-medium'">{{ t(`admin.dashboard.checklist.${step.key}`) }}</span>
              <span v-if="step.optional" class="ml-1 text-xs text-ink-900/60">({{ t('admin.dashboard.checklist.optional') }})</span>
              <p v-if="!step.done" class="text-sm text-ink-900/70">{{ t(`admin.dashboard.checklist.${step.key}Help`) }}</p>
            </div>
            <v-btn v-if="!step.done && step.to" size="small" variant="tonal" :to="step.to">{{ t('admin.dashboard.checklist.go') }}</v-btn>
          </li>
        </ul>
      </v-card>

      <div class="mt-6 grid grid-cols-2 gap-4 md:grid-cols-5">
        <v-card v-for="count in counts" :key="count.key" rounded="lg" elevation="0" border class="pa-4">
          <p class="text-sm text-ink-900/70">{{ t(`admin.dashboard.counts.${count.key}`) }}</p>
          <p class="mt-1 font-display text-3xl font-bold" :class="count.value && count.color === 'failed' ? 'text-failed-600' : ''">
            {{ count.value }}
          </p>
        </v-card>
      </div>

      <div class="mt-6 grid gap-6 lg:grid-cols-2">
        <v-card v-for="list in (['waiting', 'failed'] as const)" :key="list" rounded="lg" elevation="0" border>
          <v-card-title class="font-display">{{ t(`admin.dashboard.lists.${list}`) }}</v-card-title>
          <v-list v-if="board[list].length" lines="two">
            <v-list-item v-for="report in board[list]" :key="report.id" :to="`/admin/reports/${report.id}`">
              <v-list-item-title>{{ report.document_type_name ?? t('admin.reports.noType') }} · {{ report.requester }}</v-list-item-title>
              <v-list-item-subtitle>{{ report.error_detail ?? formatDateTime(report.created_at) }}</v-list-item-subtitle>
              <template #append>
                <v-chip :color="statusColor(report.status)" size="small" variant="tonal">{{ statusLabel(report.status) }}</v-chip>
              </template>
            </v-list-item>
          </v-list>
          <v-card-text v-else class="text-ink-900/60">{{ t(`admin.dashboard.lists.${list}Empty`) }}</v-card-text>
        </v-card>
      </div>
    </template>
  </div>
</template>
