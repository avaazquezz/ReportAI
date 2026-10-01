<script setup lang="ts">
import type { CheckResult, EmailSettings, EmailSettingsResponse, SmtpSecurity } from '~/types'

const { t } = useI18n()
const api = useApi()
const { show } = useSnackbar()
const authStore = useAuthStore()

const loaded = ref<EmailSettingsResponse | null>(null)
const loadError = ref('')
const smtp = reactive<EmailSettings>({ host: '', port: 587, security: 'starttls', user: '', password: '', from_address: '' })
const form = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)
const saving = ref(false)
const checking = ref(false)
const result = ref<CheckResult | null>(null)
const testTo = ref(authStore.user?.email ?? '')
const required = (v: unknown) => (v !== null && v !== undefined && String(v).trim() !== '') || t('admin.common.validation.required')
const email = (v: string) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v ?? '') || t('admin.common.validation.email')

const SECURITY = computed<{ value: SmtpSecurity; title: string }[]>(() => [
  { value: 'starttls', title: 'STARTTLS (587)' },
  { value: 'ssl', title: 'SSL/TLS (465)' },
  { value: 'none', title: t('admin.settings.email.noEncryption') }
])

function fill(settings: EmailSettingsResponse) {
  loaded.value = settings
  const { host, port, security, user, from_address } = settings
  Object.assign(smtp, { host, port, security, user, from_address, password: '' })
}

// A blank password keeps the saved one: the API never sends it back.
const body = () => ({ ...smtp, password: smtp.password?.trim() ? smtp.password : null })

function errorText(err: unknown, fallback: string) {
  const detail = (err as { data?: { detail?: unknown } })?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

async function save() {
  if (!(await form.value?.validate())?.valid) return
  saving.value = true
  try {
    fill(await api<EmailSettingsResponse>('/instance/email', { method: 'PUT', body: body() }))
    show(t('admin.settings.saved'), 'success')
  } catch (err) {
    show(errorText(err, t('admin.settings.email.errors.save')), 'error')
  } finally {
    saving.value = false
  }
}

async function sendTest() {
  if (!(await form.value?.validate())?.valid) return
  checking.value = true
  result.value = null
  try {
    result.value = await api<CheckResult>('/instance/email/check', { method: 'POST', body: { to: testTo.value, settings: body() } })
  } catch (err) {
    result.value = { ok: false, reason: null, detail: errorText(err, t('admin.settings.checkFailed')) }
  } finally {
    checking.value = false
  }
}

onMounted(async () => {
  try {
    fill(await api<EmailSettingsResponse>('/instance/email'))
  } catch {
    loadError.value = t('admin.settings.email.errors.load')
  }
})
</script>

<template>
  <div>
    <v-alert v-if="loadError" type="error" variant="tonal">{{ loadError }}</v-alert>
    <v-progress-linear v-else-if="!loaded" indeterminate color="primary" />
    <v-form v-else ref="form" @submit.prevent="save">
      <p class="mb-4 text-sm text-ink-900/70">{{ t('admin.settings.email.help') }}</p>
      <div class="grid gap-4 md:grid-cols-3">
        <v-text-field v-model="smtp.host" class="md:col-span-2" :label="t('admin.settings.email.host')" :rules="[required]" />
        <v-text-field v-model.number="smtp.port" :label="t('admin.settings.email.port')" type="number" :rules="[required]" />
      </div>
      <v-select v-model="smtp.security" :items="SECURITY" :label="t('admin.settings.email.security')" />
      <div class="grid gap-4 md:grid-cols-2">
        <v-text-field v-model="smtp.user" :label="t('admin.settings.email.user')" autocomplete="off" />
        <v-text-field
          v-model="smtp.password"
          :label="t('admin.settings.email.password')"
          :placeholder="loaded.password.is_set ? t('admin.settings.keepSecret', { hint: loaded.password.hint ?? '' }) : ''"
          persistent-placeholder
          type="password"
          autocomplete="off"
        />
      </div>
      <v-text-field v-model="smtp.from_address" :label="t('admin.settings.email.from')" :rules="[required, email]" />
      <div class="flex flex-wrap items-center gap-3">
        <v-text-field v-model="testTo" class="max-w-xs" density="compact" hide-details :label="t('admin.settings.email.testTo')" />
        <v-btn variant="tonal" :loading="checking" @click="sendTest">{{ t('admin.settings.email.sendTest') }}</v-btn>
        <CheckOutcome v-if="result?.ok" :result="result" :ok-text="t('admin.settings.email.sent')" />
      </div>
      <CheckOutcome v-if="result && !result.ok" :result="result" />
      <div class="mt-6 flex justify-end">
        <v-btn type="submit" color="primary" :loading="saving">{{ t('admin.common.save') }}</v-btn>
      </div>
    </v-form>
  </div>
</template>
