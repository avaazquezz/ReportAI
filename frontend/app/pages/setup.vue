<script setup lang="ts">
import type { CheckResult, EmailSettings, ExtractionSettings, SmtpSecurity, TokenResponse, TranscriptionSettings } from '~/types'

definePageMeta({ layout: 'auth', titleKey: 'setup.title' })

const { t, locale } = useI18n()
const authStore = useAuthStore()
const { markSetUp } = useInstance()
const api = useApi()

type FormRef = { validate: () => Promise<{ valid: boolean }> } | null

const STEPS = ['code', 'company', 'ai', 'email', 'telegram'] as const
const step = ref(0)
const forms = ref<FormRef[]>([])
const error = ref('')

const required = (v: unknown) => (v !== null && v !== undefined && String(v).trim() !== '') || t('setup.validation.required')
const email = (v: string) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v ?? '') || t('setup.validation.email')

function apiError(err: unknown, fallback: string): string {
  const detail = (err as { data?: { detail?: unknown } })?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

// ── 1. The code printed on the server ──────────────────────────────────────────────────
const code = ref('')

// ── 2. The company and its administrator ──────────────────────────────────────────────
const timezones = Intl.supportedValuesOf('timeZone')
const company = reactive({
  name: '',
  language: (locale.value === 'en' ? 'en' : 'es') as 'es' | 'en',
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Madrid'
})
// The bot speaks the panel's language unless chosen here: switching the panel to Spanish on
// step 1 must not leave the company in English.
const languageChosen = ref(false)
watch(locale, (value) => {
  if (!languageChosen.value) company.language = value === 'en' ? 'en' : 'es'
})
const admin = reactive({ full_name: '', email: '', password: '', confirm: '' })
const minLength = (v: string) => (v ?? '').length >= 8 || t('setup.validation.password')
const sameAsPassword = (v: string) => v === admin.password || t('setup.validation.confirm')

// ── 3. AI: who reads the messages, and who turns voice notes into text ─────────────────
type Preset = { key: string; extraction: Omit<ExtractionSettings, 'api_key'> }
const AI_PRESETS: Preset[] = [
  { key: 'anthropic', extraction: { provider: 'anthropic', model: 'claude-sonnet-5', base_url: '', effort: '' } },
  { key: 'openai', extraction: { provider: 'openai_compatible', model: '', base_url: 'https://api.openai.com/v1', effort: '' } },
  { key: 'deepseek', extraction: { provider: 'openai_compatible', model: 'deepseek-chat', base_url: 'https://api.deepseek.com', effort: '' } },
  { key: 'other', extraction: { provider: 'openai_compatible', model: '', base_url: '', effort: '' } }
]
const aiPreset = ref('anthropic')
const extraction = reactive<ExtractionSettings>({ ...AI_PRESETS[0]!.extraction, api_key: '' })
watch(aiPreset, (key) => Object.assign(extraction, AI_PRESETS.find((p) => p.key === key)!.extraction))

const VOICE_PRESETS: Record<string, Omit<TranscriptionSettings, 'api_key'>> = {
  groq: { base_url: 'https://api.groq.com/openai/v1', model: 'whisper-large-v3-turbo' },
  openai: { base_url: 'https://api.openai.com/v1', model: 'whisper-1' },
  other: { base_url: '', model: '' }
}
const voiceEnabled = ref(true)
const voicePreset = ref('groq')
const transcription = reactive<TranscriptionSettings>({ ...VOICE_PRESETS.groq!, api_key: '' })
watch(voicePreset, (key) => Object.assign(transcription, VOICE_PRESETS[key]))

const aiCheck = ref<CheckResult | null>(null)
const voiceCheck = ref<CheckResult | null>(null)
const checking = ref<string | null>(null)

async function check(what: 'ai' | 'voice') {
  checking.value = what
  const target = what === 'ai' ? aiCheck : voiceCheck
  target.value = null
  try {
    target.value = await api<CheckResult>('/setup/check-ai', {
      method: 'POST',
      body: {
        code: code.value,
        language: company.language,
        ...(what === 'ai' ? { extraction } : { transcription })
      }
    })
  } catch (err) {
    target.value = failedCheck(err, t('setup.errors.check'))
  } finally {
    checking.value = null
  }
}

// ── 4. Email (optional) ────────────────────────────────────────────────────────────────
const emailEnabled = ref(false)
const smtp = reactive<EmailSettings>({ host: '', port: 587, security: 'starttls', user: '', password: '', from_address: '' })
const SECURITY = computed<{ value: SmtpSecurity; title: string }[]>(() => [
  { value: 'starttls', title: 'STARTTLS (587)' },
  { value: 'ssl', title: 'SSL/TLS (465)' },
  { value: 'none', title: t('setup.email.noEncryption') }
])
const emailCheck = ref<CheckResult | null>(null)

async function checkEmail() {
  checking.value = 'email'
  emailCheck.value = null
  try {
    emailCheck.value = await api<CheckResult>('/setup/check-email', {
      method: 'POST',
      body: { code: code.value, to: admin.email, settings: smtp }
    })
  } catch (err) {
    emailCheck.value = failedCheck(err, t('setup.errors.check'))
  } finally {
    checking.value = null
  }
}

// ── 5. Telegram (optional) ─────────────────────────────────────────────────────────────
const botToken = ref('')
const botUsername = ref('')
const botError = ref('')

async function checkBot() {
  checking.value = 'telegram'
  botError.value = ''
  botUsername.value = ''
  try {
    const bot = await api<{ username: string }>('/setup/check-telegram', {
      method: 'POST',
      body: { code: code.value, bot_token: botToken.value }
    })
    botUsername.value = bot.username
  } catch (err) {
    const status = (err as { response?: Response }).response?.status
    botError.value = status === 400 ? t('setup.telegram.rejected') : apiError(err, t('setup.errors.check'))
  } finally {
    checking.value = null
  }
}

// ── Moving through the steps ───────────────────────────────────────────────────────────
const busy = ref(false)

async function next() {
  error.value = ''
  if (!(await forms.value[step.value]?.validate())?.valid) return
  if (STEPS[step.value] === 'code') {
    busy.value = true
    try {
      await api('/setup/verify', { method: 'POST', body: { code: code.value } })
    } catch (err) {
      const status = (err as { response?: Response }).response?.status
      error.value = status === 429 ? t('setup.errors.tooMany') : status === 409 ? apiError(err, t('setup.errors.code')) : t('setup.errors.code')
      return
    } finally {
      busy.value = false
    }
  }
  if (step.value < STEPS.length - 1) step.value++
  else await finish()
}

async function finish() {
  busy.value = true
  try {
    const tokens = await api<TokenResponse>('/setup/complete', {
      method: 'POST',
      body: {
        code: code.value,
        company,
        admin: { full_name: admin.full_name, email: admin.email, password: admin.password },
        extraction,
        transcription: voiceEnabled.value ? transcription : null,
        email: emailEnabled.value ? smtp : null,
        telegram_bot_token: botToken.value.trim() || null
      }
    })
    markSetUp()
    await authStore.applySession(tokens)
    await navigateTo('/dashboard')
  } catch (err) {
    error.value = apiError(err, t('setup.errors.finish'))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-2xl px-6 pb-24 pt-6">
    <h1 class="font-display text-3xl font-bold text-ink-900">{{ t('setup.title') }}</h1>
    <p class="mt-2 text-ink-900/70">{{ t('setup.intro') }}</p>

    <ol class="mt-8 flex list-none flex-wrap gap-2 p-0" :aria-label="t('setup.progress')">
      <li
        v-for="(name, i) in STEPS"
        :key="name"
        class="rounded-full px-3 py-1 text-sm"
        :class="i === step ? 'bg-capture-600 text-white' : i < step ? 'bg-capture-100 text-ink-900' : 'bg-surface-0 text-ink-900/60'"
        :aria-current="i === step ? 'step' : undefined"
      >
        {{ i + 1 }}. {{ t(`setup.steps.${name}`) }}
      </li>
    </ol>

    <v-card class="mt-6 pa-6" rounded="lg" elevation="0" border>
      <!-- 1. Code -->
      <v-form v-if="step === 0" :ref="(el) => (forms[0] = el as FormRef)" @submit.prevent="next">
        <h2 class="font-display text-xl font-bold">{{ t('setup.code.title') }}</h2>
        <p class="mb-4 mt-2 text-ink-900/70">{{ t('setup.code.help') }}</p>
        <pre class="mb-4 rounded bg-paper-100 px-3 py-2 text-sm">reportai setup-code</pre>
        <v-text-field
          v-model="code"
          :label="t('setup.code.label')"
          placeholder="ABCD-EFGH-JKLM"
          :rules="[required]"
          autocomplete="one-time-code"
          autofocus
        />
      </v-form>

      <!-- 2. Company and administrator -->
      <v-form v-else-if="step === 1" :ref="(el) => (forms[1] = el as FormRef)" @submit.prevent="next">
        <h2 class="font-display text-xl font-bold">{{ t('setup.company.title') }}</h2>
        <v-text-field v-model="company.name" class="mt-4" :label="t('setup.company.name')" :rules="[required]" />
        <div class="grid gap-4 sm:grid-cols-2">
          <v-select
            v-model="company.language"
            :items="[{ value: 'es', title: 'Español' }, { value: 'en', title: 'English' }]"
            :label="t('setup.company.language')"
            :hint="t('setup.company.languageHint')"
            persistent-hint
            @update:model-value="languageChosen = true"
          />
          <v-autocomplete v-model="company.timezone" :items="timezones" :label="t('setup.company.timezone')" :rules="[required]" />
        </div>
        <h2 class="mt-8 font-display text-xl font-bold">{{ t('setup.admin.title') }}</h2>
        <p class="mt-1 text-ink-900/70">{{ t('setup.admin.help') }}</p>
        <v-text-field v-model="admin.full_name" class="mt-4" :label="t('setup.admin.name')" :rules="[required]" autocomplete="name" />
        <v-text-field v-model="admin.email" :label="t('setup.admin.email')" type="email" :rules="[required, email]" autocomplete="email" />
        <div class="grid gap-4 sm:grid-cols-2">
          <v-text-field v-model="admin.password" :label="t('setup.admin.password')" type="password" :rules="[minLength]" autocomplete="new-password" />
          <v-text-field v-model="admin.confirm" :label="t('setup.admin.confirm')" type="password" :rules="[sameAsPassword]" autocomplete="new-password" />
        </div>
      </v-form>

      <!-- 3. AI -->
      <v-form v-else-if="step === 2" :ref="(el) => (forms[2] = el as FormRef)" @submit.prevent="next">
        <h2 class="font-display text-xl font-bold">{{ t('setup.ai.title') }}</h2>
        <p class="mt-2 text-ink-900/70">{{ t('setup.ai.help') }}</p>
        <v-select
          v-model="aiPreset"
          class="mt-4"
          :items="AI_PRESETS.map((p) => ({ value: p.key, title: t(`setup.ai.presets.${p.key}`) }))"
          :label="t('setup.ai.provider')"
        />
        <v-text-field
          v-if="extraction.provider === 'openai_compatible'"
          v-model="extraction.base_url"
          :label="t('setup.ai.baseUrl')"
          :rules="[required]"
          placeholder="https://…"
        />
        <v-text-field v-model="extraction.model" :label="t('setup.ai.model')" :rules="[required]" :hint="t('setup.ai.modelHint')" persistent-hint />
        <v-text-field
          v-model="extraction.api_key"
          class="mt-2"
          :label="t('setup.ai.apiKey')"
          type="password"
          autocomplete="off"
          :rules="[required]"
        />
        <div class="flex items-center gap-3">
          <v-btn variant="tonal" :loading="checking === 'ai'" @click="check('ai')">{{ t('setup.checkButton') }}</v-btn>
          <CheckOutcome v-if="aiCheck?.ok" :result="aiCheck" />
        </div>
        <CheckOutcome v-if="aiCheck && !aiCheck.ok" :result="aiCheck" />

        <h3 class="mt-8 font-display text-lg font-bold">{{ t('setup.voice.title') }}</h3>
        <v-switch v-model="voiceEnabled" color="primary" :label="t('setup.voice.enable')" hide-details />
        <template v-if="voiceEnabled">
          <p class="mb-3 text-sm text-ink-900/70">{{ t('setup.voice.help') }}</p>
          <v-select
            v-model="voicePreset"
            :items="Object.keys(VOICE_PRESETS).map((k) => ({ value: k, title: t(`setup.voice.presets.${k}`) }))"
            :label="t('setup.voice.provider')"
          />
          <template v-if="voicePreset === 'other'">
            <v-text-field v-model="transcription.base_url" :label="t('setup.ai.baseUrl')" :rules="[required]" />
            <v-text-field v-model="transcription.model" :label="t('setup.ai.model')" :rules="[required]" />
          </template>
          <v-text-field v-model="transcription.api_key" :label="t('setup.ai.apiKey')" type="password" autocomplete="off" :rules="[required]" />
          <div class="flex items-center gap-3">
            <v-btn variant="tonal" :loading="checking === 'voice'" @click="check('voice')">{{ t('setup.checkButton') }}</v-btn>
            <CheckOutcome v-if="voiceCheck?.ok" :result="voiceCheck" />
          </div>
          <CheckOutcome v-if="voiceCheck && !voiceCheck.ok" :result="voiceCheck" />
        </template>
      </v-form>

      <!-- 4. Email -->
      <v-form v-else-if="step === 3" :ref="(el) => (forms[3] = el as FormRef)" @submit.prevent="next">
        <h2 class="font-display text-xl font-bold">{{ t('setup.email.title') }}</h2>
        <p class="mt-2 text-ink-900/70">{{ t('setup.email.help') }}</p>
        <v-switch v-model="emailEnabled" color="primary" :label="t('setup.email.enable')" hide-details />
        <template v-if="emailEnabled">
          <div class="grid gap-4 sm:grid-cols-3">
            <v-text-field v-model="smtp.host" class="sm:col-span-2" :label="t('setup.email.host')" :rules="[required]" placeholder="smtp.example.com" />
            <v-text-field v-model.number="smtp.port" :label="t('setup.email.port')" type="number" :rules="[required]" />
          </div>
          <v-select v-model="smtp.security" :items="SECURITY" :label="t('setup.email.security')" />
          <div class="grid gap-4 sm:grid-cols-2">
            <v-text-field v-model="smtp.user" :label="t('setup.email.user')" autocomplete="off" />
            <v-text-field v-model="smtp.password" :label="t('setup.email.password')" type="password" autocomplete="off" />
          </div>
          <v-text-field v-model="smtp.from_address" :label="t('setup.email.from')" :rules="[required, email]" placeholder="informes@empresa.com" />
          <div class="flex items-center gap-3">
            <v-btn variant="tonal" :loading="checking === 'email'" @click="checkEmail">{{ t('setup.email.send', { to: admin.email }) }}</v-btn>
            <CheckOutcome v-if="emailCheck?.ok" :result="emailCheck" :ok-text="t('setup.email.sent')" />
          </div>
          <CheckOutcome v-if="emailCheck && !emailCheck.ok" :result="emailCheck" />
        </template>
      </v-form>

      <!-- 5. Telegram -->
      <v-form v-else :ref="(el) => (forms[4] = el as FormRef)" @submit.prevent="next">
        <h2 class="font-display text-xl font-bold">{{ t('setup.telegram.title') }}</h2>
        <ol class="mt-3 list-decimal space-y-1 pl-5 text-ink-900/80">
          <li>{{ t('setup.telegram.step1') }}</li>
          <li>{{ t('setup.telegram.step2') }}</li>
          <li>{{ t('setup.telegram.step3') }}</li>
        </ol>
        <v-text-field v-model="botToken" class="mt-4" :label="t('setup.telegram.token')" type="password" autocomplete="off" placeholder="123456789:AA…" />
        <div class="flex items-center gap-3">
          <v-btn variant="tonal" :disabled="!botToken.trim()" :loading="checking === 'telegram'" @click="checkBot">{{ t('setup.checkButton') }}</v-btn>
          <span v-if="botUsername" class="text-sm text-success">✓ @{{ botUsername }}</span>
        </div>
        <v-alert v-if="botError" type="error" variant="tonal" density="compact" class="mt-3">{{ botError }}</v-alert>
        <p class="mt-4 text-sm text-ink-900/70">{{ t('setup.telegram.later') }}</p>
      </v-form>

      <v-alert v-if="error" type="error" variant="tonal" class="mt-4">{{ error }}</v-alert>

      <div class="mt-6 flex justify-between">
        <v-btn v-if="step > 0" variant="text" :disabled="busy" @click="step--">{{ t('setup.back') }}</v-btn>
        <span v-else />
        <v-btn color="primary" :loading="busy" @click="next">
          {{ step === STEPS.length - 1 ? t('setup.finish') : t('setup.next') }}
        </v-btn>
      </div>
    </v-card>
  </div>
</template>
