<script setup lang="ts">
import type {
  CheckResult,
  CompanyAISettings,
  CompanyExtractionProvider,
  CompanyTranscriptionProvider,
  SecretState
} from '~/types'
import type { CompanyAiForm } from '~/utils/companyAi'

// A company's own AI on the hosted service: its admin enters the provider and key, and its reports
// are paid by that key. A one-company installation sets its AI in AiSettings instead.
const { t } = useI18n()
const api = useApi()
const { show } = useSnackbar()

const loaded = ref<CompanyAISettings | null>(null)
const draft = ref<CompanyAiForm | null>(null)
const loadError = ref('')
const form = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)
const saving = ref(false)
const checking = ref<'ai' | 'voice' | null>(null)
const aiCheck = ref<CheckResult | null>(null)
const voiceCheck = ref<CheckResult | null>(null)

const EFFORTS = computed(() => [
  { value: '', title: t('admin.settings.ai.effortDefault') },
  { value: 'low', title: t('admin.settings.ai.effortLow') },
  { value: 'medium', title: t('admin.settings.ai.effortMedium') },
  { value: 'high', title: t('admin.settings.ai.effortHigh') }
])
const extractionItems = computed(() => loaded.value?.extraction_providers.map((p) => ({ value: p.id, title: p.name })) ?? [])
const transcriptionItems = computed(() => loaded.value?.transcription_providers.map((p) => ({ value: p.id, title: p.name })) ?? [])
const notValidated = computed(
  () => loaded.value?.extraction_providers.find((p) => p.id === draft.value?.extraction.provider)?.validated === false
)
const extractionKept = computed(() =>
  loaded.value && draft.value ? keptKey(loaded.value.extraction, draft.value.extraction.provider) : null
)
const transcriptionKept = computed(() =>
  loaded.value && draft.value ? keptKey(loaded.value.transcription, draft.value.transcription.provider) : null
)

const required = (v: string) => Boolean(v?.trim()) || t('admin.common.validation.required')
// A blank key field is fine only when a key is saved for the provider picked.
const keyRule = (kept: SecretState | null) => (v: string) => Boolean(kept) || required(v)
const keepSecret = (kept: SecretState | null) => (kept ? t('admin.settings.keepSecret', { hint: kept.hint ?? '' }) : '')

function fill(settings: CompanyAISettings) {
  loaded.value = settings
  // On the platform's AI there is nothing to set up, so no form to fill.
  draft.value = settings.platform_ai ? null : companyAiForm(settings)
}

function pickExtraction(id: CompanyExtractionProvider) {
  const option = loaded.value?.extraction_providers.find((p) => p.id === id)
  if (draft.value && option) draft.value.extraction = withProvider(draft.value.extraction, option)
  aiCheck.value = null
}

function pickTranscription(id: CompanyTranscriptionProvider) {
  const option = loaded.value?.transcription_providers.find((p) => p.id === id)
  if (draft.value && option) draft.value.transcription = withProvider(draft.value.transcription, option)
  voiceCheck.value = null
}

function errorText(err: unknown, fallback: string) {
  const detail = (err as { data?: { detail?: unknown } })?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

async function check(what: 'ai' | 'voice') {
  if (!draft.value) return
  const target = what === 'ai' ? aiCheck : voiceCheck
  const typedKey = what === 'ai' ? draft.value.extraction.api_key : draft.value.transcription.api_key
  const kept = what === 'ai' ? extractionKept.value : transcriptionKept.value
  // Nothing to try without a key: said here, in the reader's language, not with the API's message.
  if (!typedKey.trim() && !kept) {
    target.value = { ok: false, reason: 'not_configured', detail: null }
    return
  }
  checking.value = what
  target.value = null
  try {
    target.value = await api<CheckResult>('/company/ai/check', { method: 'POST', body: companyAiCheck(draft.value, what) })
  } catch (err) {
    const status = (err as { response?: Response }).response?.status
    target.value =
      status === 429
        ? { ok: false, reason: null, detail: t('admin.settings.companyAi.tooManyChecks') }
        : failedCheck(err, t('admin.settings.checkFailed'))
  } finally {
    checking.value = null
  }
}

async function save() {
  if (!draft.value || !(await form.value?.validate())?.valid) return
  saving.value = true
  try {
    fill(await api<CompanyAISettings>('/company/ai', { method: 'PUT', body: companyAiUpdate(draft.value) }))
    show(t('admin.settings.saved'), 'success')
  } catch (err) {
    show(errorText(err, t('admin.settings.ai.errors.save')), 'error')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    fill(await api<CompanyAISettings>('/company/ai'))
  } catch {
    loadError.value = t('admin.settings.ai.errors.load')
  }
})
</script>

<template>
  <div>
    <v-alert v-if="loadError" type="error" variant="tonal">{{ loadError }}</v-alert>
    <v-progress-linear v-else-if="!loaded" indeterminate color="primary" />
    <v-alert v-else-if="loaded.platform_ai" type="info" variant="tonal">{{ t('admin.settings.companyAi.platform') }}</v-alert>
    <v-form v-else-if="draft" ref="form" @submit.prevent="save">
      <p class="mb-6 text-sm text-ink-900/70">{{ t('admin.settings.companyAi.intro') }}</p>

      <h3 class="font-display text-lg font-bold">{{ t('admin.settings.ai.extractionTitle') }}</h3>
      <p class="mb-4 text-sm text-ink-900/70">{{ t('admin.settings.companyAi.extractionHelp') }}</p>
      <div class="grid gap-4 md:grid-cols-2">
        <v-select
          :model-value="draft.extraction.provider"
          :items="extractionItems"
          :label="t('admin.settings.ai.provider')"
          :hint="notValidated ? t('admin.settings.companyAi.notValidated') : undefined"
          persistent-hint
          @update:model-value="pickExtraction"
        />
        <v-text-field v-model="draft.extraction.model" :label="t('admin.settings.ai.model')" :rules="[required]" />
      </div>
      <v-select
        v-if="draft.extraction.provider === 'anthropic'"
        v-model="draft.extraction.effort"
        :items="EFFORTS"
        :label="t('admin.settings.ai.effort')"
      />
      <v-text-field
        v-model="draft.extraction.api_key"
        :label="t('admin.settings.ai.apiKey')"
        :placeholder="keepSecret(extractionKept)"
        :rules="[keyRule(extractionKept)]"
        persistent-placeholder
        type="password"
        autocomplete="off"
      />
      <div class="flex items-center gap-3">
        <v-btn variant="tonal" :loading="checking === 'ai'" @click="check('ai')">{{ t('admin.settings.check') }}</v-btn>
        <CheckOutcome v-if="aiCheck?.ok" :result="aiCheck" />
      </div>
      <CheckOutcome v-if="aiCheck && !aiCheck.ok" :result="aiCheck" />

      <v-divider class="my-6" />
      <h3 class="font-display text-lg font-bold">{{ t('admin.settings.ai.voiceTitle') }}</h3>
      <p class="text-sm text-ink-900/70">{{ t('admin.settings.companyAi.voiceHelp') }}</p>
      <v-switch v-model="draft.voice" color="primary" :label="t('admin.settings.companyAi.voiceEnable')" hide-details />
      <template v-if="draft.voice">
        <div class="mt-2 grid gap-4 md:grid-cols-2">
          <v-select
            :model-value="draft.transcription.provider"
            :items="transcriptionItems"
            :label="t('admin.settings.ai.provider')"
            @update:model-value="pickTranscription"
          />
          <v-text-field v-model="draft.transcription.model" :label="t('admin.settings.ai.model')" :rules="[required]" />
        </div>
        <v-text-field
          v-model="draft.transcription.api_key"
          :label="t('admin.settings.ai.apiKey')"
          :placeholder="keepSecret(transcriptionKept)"
          :rules="[keyRule(transcriptionKept)]"
          persistent-placeholder
          type="password"
          autocomplete="off"
        />
        <div class="flex items-center gap-3">
          <v-btn variant="tonal" :loading="checking === 'voice'" @click="check('voice')">{{ t('admin.settings.check') }}</v-btn>
          <CheckOutcome v-if="voiceCheck?.ok" :result="voiceCheck" />
        </div>
        <CheckOutcome v-if="voiceCheck && !voiceCheck.ok" :result="voiceCheck" />
      </template>

      <div class="mt-6 flex justify-end">
        <v-btn type="submit" color="primary" :loading="saving">{{ t('admin.common.save') }}</v-btn>
      </div>
    </v-form>
  </div>
</template>
