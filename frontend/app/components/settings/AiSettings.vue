<script setup lang="ts">
import type { AISettings, CheckResult, ExtractionSettings, TranscriptionSettings } from '~/types'

const { t } = useI18n()
const api = useApi()
const { show } = useSnackbar()

const loaded = ref<AISettings | null>(null)
const loadError = ref('')
const extraction = reactive<ExtractionSettings>({ provider: 'anthropic', model: '', base_url: '', effort: '', api_key: '' })
const transcription = reactive<TranscriptionSettings>({ base_url: '', model: '', api_key: '' })
const form = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)
const saving = ref(false)
const checking = ref<'ai' | 'voice' | null>(null)
const aiCheck = ref<CheckResult | null>(null)
const voiceCheck = ref<CheckResult | null>(null)
const required = (v: string) => Boolean(v?.trim()) || t('admin.common.validation.required')

const PROVIDERS = computed(() => [
  { value: 'anthropic', title: 'Anthropic Claude' },
  { value: 'openai_compatible', title: t('admin.settings.ai.openaiCompatible') }
])
const EFFORTS = computed(() => [
  { value: '', title: t('admin.settings.ai.effortDefault') },
  { value: 'low', title: t('admin.settings.ai.effortLow') },
  { value: 'medium', title: t('admin.settings.ai.effortMedium') },
  { value: 'high', title: t('admin.settings.ai.effortHigh') }
])

function fill(settings: AISettings) {
  loaded.value = settings
  const { provider, model, base_url, effort } = settings.extraction
  Object.assign(extraction, { provider, model, base_url, effort, api_key: '' })
  Object.assign(transcription, { base_url: settings.transcription.base_url, model: settings.transcription.model, api_key: '' })
}

// A blank key field keeps the saved key: the API never sends one back.
function payload() {
  return {
    extraction: { ...extraction, api_key: extraction.api_key?.trim() || null },
    transcription: { ...transcription, api_key: transcription.api_key?.trim() || null }
  }
}

function errorText(err: unknown, fallback: string) {
  const detail = (err as { data?: { detail?: unknown } })?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

async function check(what: 'ai' | 'voice') {
  checking.value = what
  const target = what === 'ai' ? aiCheck : voiceCheck
  target.value = null
  try {
    const body = payload()
    target.value = await api<CheckResult>('/instance/ai/check', {
      method: 'POST',
      body: what === 'ai' ? { extraction: body.extraction } : { transcription: body.transcription }
    })
  } catch (err) {
    target.value = { ok: false, reason: null, detail: errorText(err, t('admin.settings.checkFailed')) }
  } finally {
    checking.value = null
  }
}

async function save() {
  if (!(await form.value?.validate())?.valid) return
  saving.value = true
  try {
    fill(await api<AISettings>('/instance/ai', { method: 'PUT', body: payload() }))
    show(t('admin.settings.saved'), 'success')
  } catch (err) {
    show(errorText(err, t('admin.settings.ai.errors.save')), 'error')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    fill(await api<AISettings>('/instance/ai'))
  } catch {
    loadError.value = t('admin.settings.ai.errors.load')
  }
})
</script>

<template>
  <div>
    <v-alert v-if="loadError" type="error" variant="tonal">{{ loadError }}</v-alert>
    <v-progress-linear v-else-if="!loaded" indeterminate color="primary" />
    <v-form v-else ref="form" @submit.prevent="save">
      <h3 class="font-display text-lg font-bold">{{ t('admin.settings.ai.extractionTitle') }}</h3>
      <p class="mb-4 text-sm text-ink-900/70">{{ t('admin.settings.ai.extractionHelp') }}</p>
      <div class="grid gap-4 md:grid-cols-2">
        <v-select v-model="extraction.provider" :items="PROVIDERS" :label="t('admin.settings.ai.provider')" />
        <v-text-field v-model="extraction.model" :label="t('admin.settings.ai.model')" :rules="[required]" />
      </div>
      <v-text-field
        v-if="extraction.provider === 'openai_compatible'"
        v-model="extraction.base_url"
        :label="t('admin.settings.ai.baseUrl')"
        :rules="[required]"
        placeholder="https://…"
      />
      <v-select v-else v-model="extraction.effort" :items="EFFORTS" :label="t('admin.settings.ai.effort')" />
      <v-text-field
        v-model="extraction.api_key"
        :label="t('admin.settings.ai.apiKey')"
        :placeholder="loaded.extraction.api_key.is_set ? t('admin.settings.keepSecret', { hint: loaded.extraction.api_key.hint ?? '' }) : ''"
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
      <p class="mb-4 text-sm text-ink-900/70">{{ t('admin.settings.ai.voiceHelp') }}</p>
      <div class="grid gap-4 md:grid-cols-2">
        <v-text-field v-model="transcription.base_url" :label="t('admin.settings.ai.baseUrl')" :rules="[required]" />
        <v-text-field v-model="transcription.model" :label="t('admin.settings.ai.model')" :rules="[required]" />
      </div>
      <v-text-field
        v-model="transcription.api_key"
        :label="t('admin.settings.ai.apiKey')"
        :placeholder="loaded.transcription.api_key.is_set ? t('admin.settings.keepSecret', { hint: loaded.transcription.api_key.hint ?? '' }) : ''"
        persistent-placeholder
        type="password"
        autocomplete="off"
      />
      <div class="flex items-center gap-3">
        <v-btn variant="tonal" :loading="checking === 'voice'" @click="check('voice')">{{ t('admin.settings.check') }}</v-btn>
        <CheckOutcome v-if="voiceCheck?.ok" :result="voiceCheck" />
      </div>
      <CheckOutcome v-if="voiceCheck && !voiceCheck.ok" :result="voiceCheck" />

      <div class="mt-6 flex justify-end">
        <v-btn type="submit" color="primary" :loading="saving">{{ t('admin.common.save') }}</v-btn>
      </div>
    </v-form>
  </div>
</template>
