<script setup lang="ts">
import type { FieldValue, ReportDelivery, ReportDetail } from '~/types'

definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app', titleKey: 'admin.reports.detail.title' })

const { t, te } = useI18n()
const route = useRoute()
const reportId = String(route.params.id)
const { formatDateTime } = useLocaleDate()
const { statusLabel, statusColor } = useReportStatus()
const { getById, approve, reject, editFields, preview, resend, fetchBlob } = useReports()
const { show } = useSnackbar()
const authStore = useAuthStore()
const isDemo = computed(() => authStore.user?.is_demo ?? false)

const POLL_MS = 3000

const report = ref<ReportDetail | null>(null)
const loadError = ref('')
const fields = ref<Record<string, FieldValue>>({})
const busy = ref<string | null>(null)

const audioUrl = ref<string | null>(null)
const photoUrls = ref<Record<string, string>>({})
const previewUrl = ref<string | null>(null)

const schema = computed(() => report.value?.field_schema ?? {})
const original = computed(() => report.value?.extracted_fields ?? {})
const edits = computed(() =>
  Object.fromEntries(
    Object.entries(fields.value).filter(
      ([name, value]) => JSON.stringify(value ?? null) !== JSON.stringify(original.value[name] ?? null)
    )
  )
)
const dirty = computed(() => Object.keys(edits.value).length > 0)
const status = computed(() => report.value?.status ?? '')
const awaitingApproval = computed(() => status.value === 'awaiting_approval')
const delivered = computed(() => FINISHED_STATUSES.includes(status.value))
const editable = computed(() => !isDemo.value && (awaitingApproval.value || delivered.value))
const rejectable = computed(() => !isDemo.value && PAUSED_STATUSES.includes(status.value))
const failedDeliveries = computed(() => report.value?.deliveries.filter((d) => d.status === 'failed') ?? [])

const missing = computed(() =>
  Object.entries(schema.value)
    .filter(([name, spec]) => {
      if (spec.type === 'image' || !spec.required) return false
      const value = fields.value[name]
      return value === null || value === undefined || (typeof value === 'string' && !value.trim())
    })
    .map(([name, spec]) => spec.label || name)
)

const totalCost = computed(() => report.value?.steps.reduce((sum, step) => sum + (step.cost_usd ?? 0), 0) ?? 0)

type TimelineItem = { at: string; icon: string; color: string; title: string; detail: string | null }

function stepTitle(step: string) {
  const key = `admin.reports.steps.${step}`
  return te(key) ? t(key) : step.replace(/_/g, ' ')
}

function describeChanges(changes: Record<string, { from: unknown; to: unknown }> | null) {
  if (!changes) return null
  const text = (value: unknown) => (value === null || value === undefined || value === '' ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value))
  return Object.entries(changes)
    .map(([name, change]) => `${schema.value[name]?.label || name}: ${text(change.from)} → ${text(change.to)}`)
    .join(' · ')
}

const timeline = computed<TimelineItem[]>(() => {
  if (!report.value) return []
  const steps = report.value.steps.map((step) => ({
    at: step.created_at,
    icon: step.status === 'failed' ? 'mdi-alert-circle-outline' : step.status === 'interrupted' ? 'mdi-pause-circle-outline' : 'mdi-check-circle-outline',
    color: step.status === 'failed' ? 'failed' : 'default',
    title: stepTitle(step.step),
    detail: step.error_detail
  }))
  const revisions = report.value.revisions.map((revision) => ({
    at: revision.created_at,
    icon: 'mdi-account-edit-outline',
    color: 'primary',
    title: t(`admin.reports.revisions.${revision.action}`, { name: revision.user_name ?? t('admin.reports.revisions.someone') }),
    detail: describeChanges(revision.changes) ?? revision.note
  }))
  return [...steps, ...revisions].sort((a, b) => a.at.localeCompare(b.at))
})

function applyReport(next: ReportDetail, { keepEdits = false } = {}) {
  report.value = next
  if (!keepEdits) fields.value = structuredClone(toRaw(next.extracted_fields ?? {}))
}

function revokeAll() {
  for (const url of [audioUrl.value, previewUrl.value, ...Object.values(photoUrls.value)]) {
    if (url) URL.revokeObjectURL(url)
  }
}

async function loadMedia(detail: ReportDetail) {
  if (detail.audio_url) {
    fetchBlob(detail.audio_url).then((blob) => (audioUrl.value = URL.createObjectURL(blob))).catch(() => {})
  }
  for (const photo of detail.photos) {
    fetchBlob(photo.url)
      .then((blob) => (photoUrls.value = { ...photoUrls.value, [photo.id]: URL.createObjectURL(blob) }))
      .catch(() => {})
  }
}

// While the worker has the report, or a copy is still on its way, check back until it settles.
let pollTimer: ReturnType<typeof setTimeout> | undefined
function schedulePoll() {
  clearTimeout(pollTimer)
  const settling = status.value === 'pending' || report.value?.deliveries.some((d) => d.status === 'pending')
  if (!settling) return
  pollTimer = setTimeout(async () => {
    try {
      applyReport(await getById(reportId), { keepEdits: dirty.value })
    } catch {
      // A missed poll is retried by the next one.
    }
    schedulePoll()
  }, POLL_MS)
}

async function run(action: string, work: () => Promise<ReportDetail>, success: string) {
  busy.value = action
  try {
    applyReport(await work())
    show(t(success), 'success')
    schedulePoll()
  } catch (err) {
    const detail = (err as { data?: { detail?: unknown } })?.data?.detail
    show(typeof detail === 'string' ? detail : t(`admin.reports.errors.${action}`), 'error')
  } finally {
    busy.value = null
  }
}

const onApprove = () => run('approve', () => approve(reportId, edits.value), 'admin.reports.toast.approved')
const onSave = () =>
  run('save', () => editFields(reportId, edits.value), dirty.value ? 'admin.reports.toast.saved' : 'admin.reports.toast.regenerated')
const onResendFailed = () => run('resend', () => resend(reportId), 'admin.reports.toast.resent')
const onResendOne = (delivery: ReportDelivery) =>
  run('resend', () => resend(reportId, { delivery_id: delivery.id }), 'admin.reports.toast.resent')

const rejectDialog = ref(false)
const rejectReason = ref('')
async function onReject() {
  rejectDialog.value = false
  await run('reject', () => reject(reportId, rejectReason.value.trim() || null), 'admin.reports.toast.rejected')
  rejectReason.value = ''
}

const sendToDialog = ref(false)
const sendToEmail = ref('')
const sendToForm = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)
const emailRules = [(value: string) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value) || t('admin.reports.errors.email')]
async function onSendTo() {
  if (!(await sendToForm.value?.validate())?.valid) return
  sendToDialog.value = false
  await run('resend', () => resend(reportId, { email: sendToEmail.value.trim() }), 'admin.reports.toast.resent')
  sendToEmail.value = ''
}

const previewDialog = ref(false)
async function onPreview() {
  busy.value = 'preview'
  try {
    const blob = await preview(reportId, edits.value)
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = URL.createObjectURL(blob)
    previewDialog.value = true
  } catch (err) {
    const detail = (err as { data?: { detail?: unknown } })?.data?.detail
    show(typeof detail === 'string' ? detail : t('admin.reports.errors.preview'), 'error')
  } finally {
    busy.value = null
  }
}

async function onDownload() {
  if (!report.value?.download_url) return
  try {
    const blob = await fetchBlob(report.value.download_url)
    saveBlob(blob, `${report.value.document_type_name ?? 'report'} ${report.value.created_at.slice(0, 10)}.pdf`)
  } catch {
    show(t('admin.reports.errors.download'), 'error')
  }
}

function discard() {
  fields.value = structuredClone(toRaw(original.value))
}

onMounted(async () => {
  try {
    const detail = await getById(reportId)
    applyReport(detail)
    loadMedia(detail)
    schedulePoll()
  } catch {
    loadError.value = t('admin.reports.errors.load')
  }
})

onBeforeUnmount(() => {
  clearTimeout(pollTimer)
  revokeAll()
})
</script>

<template>
  <div>
    <v-btn variant="text" to="/admin/reports" class="mb-4" prepend-icon="mdi-arrow-left">
      {{ t('admin.layout.nav.reports') }}
    </v-btn>

    <v-alert v-if="loadError" type="error" variant="tonal">{{ loadError }}</v-alert>
    <v-skeleton-loader v-else-if="!report" type="article, card" />

    <template v-else>
      <div class="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 class="font-display text-2xl font-bold text-ink-900">
            {{ report.document_type_name ?? t('admin.reports.noType') }}
          </h1>
          <p class="mt-1 font-body text-sm text-ink-900/70">
            {{ t('admin.reports.detail.from', { who: report.requester_identifier, channel: report.requester_channel }) }}
            · {{ formatDateTime(report.received_at ?? report.created_at) }}
          </p>
        </div>
        <v-chip :color="statusColor(report.status)" variant="tonal">{{ statusLabel(report.status) }}</v-chip>
      </div>

      <v-alert v-if="status === 'pending'" type="info" variant="tonal" class="mb-4">
        {{ t('admin.reports.detail.processing') }}
        <v-progress-linear indeterminate color="primary" class="mt-2" />
      </v-alert>
      <v-alert v-else-if="status === 'awaiting_details'" type="warning" variant="tonal" class="mb-4">
        {{ t('admin.reports.detail.awaitingDetails', { fields: missing.join(', ') }) }}
      </v-alert>
      <v-alert v-else-if="status === 'failed'" type="error" variant="tonal" class="mb-4">
        <template v-if="report.reject_reason">{{ t('admin.reports.detail.rejectedBecause', { reason: report.reject_reason }) }}</template>
        <template v-else>{{ report.error_detail }}</template>
      </v-alert>

      <div class="mb-6 flex flex-wrap gap-2">
        <template v-if="awaitingApproval && !isDemo">
          <v-btn color="success" :loading="busy === 'approve'" :disabled="missing.length > 0" @click="onApprove">
            {{ dirty ? t('admin.reports.actions.approveWithChanges') : t('admin.reports.actions.approve') }}
          </v-btn>
        </template>
        <template v-if="delivered && !isDemo">
          <v-btn color="primary" :loading="busy === 'save'" :disabled="missing.length > 0" @click="onSave">
            {{ dirty ? t('admin.reports.actions.saveAndRegenerate') : t('admin.reports.actions.regenerate') }}
          </v-btn>
        </template>
        <v-btn v-if="editable && report.extracted_fields" variant="tonal" :loading="busy === 'preview'" prepend-icon="mdi-eye-outline" @click="onPreview">
          {{ t('admin.reports.actions.preview') }}
        </v-btn>
        <v-btn v-if="report.download_url" variant="tonal" prepend-icon="mdi-download" @click="onDownload">
          {{ t('admin.reports.actions.downloadPdf') }}
        </v-btn>
        <v-btn v-if="dirty" variant="text" @click="discard">{{ t('admin.reports.actions.discard') }}</v-btn>
        <v-spacer />
        <v-btn v-if="rejectable" color="failed" variant="text" @click="rejectDialog = true">
          {{ t('admin.reports.actions.reject') }}
        </v-btn>
      </div>
      <p v-if="missing.length && editable" class="-mt-4 mb-6 font-body text-sm text-failed-600">
        {{ t('admin.reports.detail.fillRequired', { fields: missing.join(', ') }) }}
      </p>

      <v-row>
        <v-col cols="12" md="7">
          <v-card flat border>
            <v-card-title>{{ t('admin.reports.detail.fields') }}</v-card-title>
            <v-card-subtitle v-if="report.evidence && Object.keys(report.evidence).length">
              {{ t('admin.reports.detail.evidenceHint') }}
            </v-card-subtitle>
            <v-card-text>
              <AdminReportFieldEditor
                v-if="report.extracted_fields"
                v-model="fields"
                :schema="schema"
                :evidence="report.evidence"
                :readonly="!editable"
              />
              <p v-else class="font-body text-sm text-ink-900/70">{{ t('admin.reports.detail.noFields') }}</p>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" md="5">
          <v-card flat border class="mb-4">
            <v-card-title>{{ t('admin.reports.detail.source') }}</v-card-title>
            <v-card-text>
              <audio v-if="audioUrl" :src="audioUrl" controls class="mb-3 w-full" :aria-label="t('admin.reports.detail.audio')" />
              <p v-if="report.source_text" class="whitespace-pre-line font-body text-sm text-ink-900">{{ report.source_text }}</p>
              <p v-else class="font-body text-sm text-ink-900/70">{{ t('admin.reports.detail.noSource') }}</p>
            </v-card-text>
          </v-card>

          <v-card v-if="report.photos.length" flat border class="mb-4">
            <v-card-title>{{ t('admin.reports.detail.photos') }}</v-card-title>
            <v-card-text class="grid grid-cols-2 gap-2">
              <a
                v-for="photo in report.photos"
                :key="photo.id"
                :href="photoUrls[photo.id]"
                target="_blank"
                rel="noopener"
                class="block aspect-[4/3] overflow-hidden rounded bg-paper-100"
              >
                <img
                  v-if="photoUrls[photo.id]"
                  :src="photoUrls[photo.id]"
                  :alt="photo.caption ?? t('admin.reports.detail.photo')"
                  class="h-full w-full object-cover"
                >
              </a>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <v-card flat border class="mt-4">
        <v-card-title class="flex flex-wrap items-center justify-between gap-2">
          {{ t('admin.reports.detail.deliveries') }}
          <div v-if="delivered && !isDemo" class="flex gap-2">
            <v-btn v-if="failedDeliveries.length" size="small" variant="tonal" :loading="busy === 'resend'" @click="onResendFailed">
              {{ t('admin.reports.actions.resendFailed') }}
            </v-btn>
            <v-btn size="small" variant="text" prepend-icon="mdi-email-plus-outline" @click="sendToDialog = true">
              {{ t('admin.reports.actions.sendTo') }}
            </v-btn>
          </div>
        </v-card-title>
        <v-card-text>
          <p v-if="!report.deliveries.length" class="font-body text-sm text-ink-900/70">{{ t('admin.reports.detail.noDeliveries') }}</p>
          <v-table v-else density="compact">
            <tbody>
              <tr v-for="delivery in report.deliveries" :key="delivery.id">
                <td>
                  <v-icon :icon="delivery.kind === 'email' ? 'mdi-email-outline' : 'mdi-message-outline'" size="small" class="mr-1" aria-hidden="true" />
                  {{ delivery.destination }}
                </td>
                <td>
                  <v-chip size="small" variant="tonal" :color="delivery.status === 'sent' ? 'approved' : delivery.status === 'failed' ? 'failed' : 'pending'">
                    {{ t(`admin.reports.deliveryStatus.${delivery.status}`) }}
                  </v-chip>
                </td>
                <td class="font-body text-xs text-ink-900/70">
                  {{ delivery.sent_at ? formatDateTime(delivery.sent_at) : delivery.last_error }}
                </td>
                <td class="text-right">
                  <v-btn
                    v-if="delivered && !isDemo && delivery.status !== 'pending'"
                    size="small"
                    variant="text"
                    @click="onResendOne(delivery)"
                  >
                    {{ t('admin.reports.actions.resend') }}
                  </v-btn>
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
      </v-card>

      <v-card flat border class="mt-4">
        <v-card-title class="flex items-center justify-between">
          {{ t('admin.reports.detail.timeline') }}
          <span v-if="totalCost" class="font-body text-sm font-normal text-ink-900/70">
            {{ t('admin.reports.detail.cost', { cost: totalCost.toFixed(4) }) }}
          </span>
        </v-card-title>
        <v-card-text>
          <v-timeline side="end" density="compact" align="start">
            <v-timeline-item v-for="(item, index) in timeline" :key="index" :icon="item.icon" :dot-color="item.color" size="small">
              <div class="font-body text-sm">
                <span class="font-medium text-ink-900">{{ item.title }}</span>
                <span class="ml-2 text-xs text-ink-900/70">{{ formatDateTime(item.at) }}</span>
              </div>
              <p v-if="item.detail" class="font-body text-xs text-ink-900/70">{{ item.detail }}</p>
            </v-timeline-item>
          </v-timeline>
        </v-card-text>
      </v-card>
    </template>

    <v-dialog v-model="rejectDialog" max-width="480">
      <v-card>
        <v-card-title>{{ t('admin.reports.dialog.rejectTitle') }}</v-card-title>
        <v-card-text>
          <p class="mb-3 font-body text-sm">{{ t('admin.reports.dialog.rejectHelp') }}</p>
          <v-textarea v-model="rejectReason" :label="t('admin.reports.dialog.rejectReason')" rows="3" counter="1000" maxlength="1000" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="rejectDialog = false">{{ t('admin.common.cancel') }}</v-btn>
          <v-btn color="failed" variant="flat" :loading="busy === 'reject'" @click="onReject">{{ t('admin.reports.actions.reject') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="sendToDialog" max-width="420">
      <v-card>
        <v-form ref="sendToForm" @submit.prevent="onSendTo">
          <v-card-title>{{ t('admin.reports.dialog.sendToTitle') }}</v-card-title>
          <v-card-text>
            <v-text-field v-model="sendToEmail" type="email" :label="t('admin.reports.dialog.email')" :rules="emailRules" autofocus />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="sendToDialog = false">{{ t('admin.common.cancel') }}</v-btn>
            <v-btn type="submit" color="primary" variant="flat">{{ t('admin.reports.actions.send') }}</v-btn>
          </v-card-actions>
        </v-form>
      </v-card>
    </v-dialog>

    <v-dialog v-model="previewDialog" max-width="960">
      <v-card>
        <v-card-title class="flex items-center justify-between">
          {{ t('admin.reports.dialog.previewTitle') }}
          <v-btn icon="mdi-close" variant="text" size="small" :aria-label="t('admin.common.close')" @click="previewDialog = false" />
        </v-card-title>
        <iframe v-if="previewUrl" :src="previewUrl" :title="t('admin.reports.dialog.previewTitle')" class="h-[75vh] w-full border-0" />
      </v-card>
    </v-dialog>
  </div>
</template>
