// The rules of a company's own AI form (components/settings/CompanyAiSettings.vue): what it starts
// with and what it sends to /company/ai. Pure, so tests/companyAi.test.ts checks them on their own.
import type {
  CompanyAICheckRequest,
  CompanyAISettings,
  CompanyAISettingsUpdate,
  CompanyExtractionSettings,
  CompanyTranscriptionSettings,
  SecretState
} from '~/types'

// What the admin types. A blank key keeps the saved one: the API never sends a key back.
export interface CompanyAiForm {
  extraction: Omit<CompanyExtractionSettings, 'api_key'> & { api_key: string }
  voice: boolean
  transcription: Omit<CompanyTranscriptionSettings, 'api_key'> & { api_key: string }
}

/** The form for what the company saved; a part it never saved starts on the first provider listed,
 * with that provider's model. Voice notes start on when saved, and on a first setup (as in the
 * installation's setup wizard): taking voice notes is what ReportAI is for. */
export function companyAiForm(settings: CompanyAISettings): CompanyAiForm {
  const savedExtraction = settings.extraction_providers.find((p) => p.id === settings.extraction.provider)
  const savedTranscription = settings.transcription_providers.find((p) => p.id === settings.transcription.provider)
  const extraction = savedExtraction ?? settings.extraction_providers[0]
  const transcription = savedTranscription ?? settings.transcription_providers[0]
  if (!extraction || !transcription) throw new Error('The API listed no AI providers to choose from')
  return {
    extraction: {
      provider: extraction.id,
      model: savedExtraction ? settings.extraction.model : extraction.default_model,
      effort: savedExtraction ? settings.extraction.effort : '',
      api_key: ''
    },
    voice: Boolean(savedTranscription) || !savedExtraction,
    transcription: {
      provider: transcription.id,
      model: savedTranscription ? settings.transcription.model : transcription.default_model,
      api_key: ''
    }
  }
}

/** A part of the form once another provider is picked: that provider's model, and no key, since a
 * key saved for one provider is never sent to another. */
export function withProvider<S extends { provider: string; model: string; api_key: string }>(
  section: S,
  option: { id: S['provider']; default_model: string }
): S {
  return { ...section, provider: option.id, model: option.default_model, api_key: '' }
}

/** The key a blank field keeps for `provider`: the saved one, only if it was saved for that provider. */
export function keptKey(saved: { provider: string | null; api_key: SecretState }, provider: string): SecretState | null {
  return saved.provider === provider && saved.api_key.is_set ? saved.api_key : null
}

function extractionBody({ extraction }: CompanyAiForm): CompanyExtractionSettings {
  return {
    provider: extraction.provider,
    model: extraction.model.trim(),
    effort: extraction.provider === 'anthropic' ? extraction.effort : '',
    api_key: extraction.api_key.trim() || null
  }
}

function transcriptionBody({ transcription }: CompanyAiForm): CompanyTranscriptionSettings {
  return {
    provider: transcription.provider,
    model: transcription.model.trim(),
    api_key: transcription.api_key.trim() || null
  }
}

/** PUT /company/ai. Voice notes off sends no transcription service, which removes the saved one. */
export function companyAiUpdate(form: CompanyAiForm): CompanyAISettingsUpdate {
  return { extraction: extractionBody(form), transcription: form.voice ? transcriptionBody(form) : null }
}

/** POST /company/ai/check: one part of the form as typed, without saving it. */
export function companyAiCheck(form: CompanyAiForm, what: 'ai' | 'voice'): CompanyAICheckRequest {
  return what === 'ai' ? { extraction: extractionBody(form) } : { transcription: transcriptionBody(form) }
}
