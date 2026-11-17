// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { CompanyAISettings } from '../app/types/index.ts'
import { companyAiCheck, companyAiForm, companyAiUpdate, keptKey, withProvider } from '../app/utils/companyAi.ts'

const noKey = { is_set: false, hint: null }
const providers = {
  extraction_providers: [
    { id: 'anthropic', name: 'Anthropic Claude', default_model: 'claude-sonnet-5', validated: true },
    { id: 'openai', name: 'OpenAI', default_model: 'gpt-6.1-terra', validated: false }
  ],
  transcription_providers: [
    { id: 'groq', name: 'Groq', default_model: 'whisper-large-v3-turbo' },
    { id: 'openai', name: 'OpenAI', default_model: 'whisper-1' }
  ]
} satisfies Pick<CompanyAISettings, 'extraction_providers' | 'transcription_providers'>

// What GET /company/ai answers before the company has entered anything.
const nothingSaved: CompanyAISettings = {
  platform_ai: false,
  extraction: { provider: null, model: '', effort: '', api_key: noKey, configured: false },
  transcription: { provider: null, model: '', api_key: noKey, configured: false },
  ...providers
}
const saved: CompanyAISettings = {
  platform_ai: false,
  extraction: { provider: 'openai', model: 'gpt-6.1-mini', effort: '', api_key: { is_set: true, hint: '…1234' }, configured: true },
  transcription: { provider: null, model: '', api_key: noKey, configured: false },
  ...providers
}

test('a first setup starts on the first provider listed, its model, and voice notes on', () => {
  assert.deepEqual(companyAiForm(nothingSaved), {
    extraction: { provider: 'anthropic', model: 'claude-sonnet-5', effort: '', api_key: '' },
    voice: true,
    transcription: { provider: 'groq', model: 'whisper-large-v3-turbo', api_key: '' }
  })
})

test('what the company saved comes back, with voice notes off when it saved none, and no key', () => {
  assert.deepEqual(companyAiForm(saved), {
    extraction: { provider: 'openai', model: 'gpt-6.1-mini', effort: '', api_key: '' },
    voice: false,
    transcription: { provider: 'groq', model: 'whisper-large-v3-turbo', api_key: '' }
  })
  const withVoice: CompanyAISettings = {
    ...saved,
    transcription: { provider: 'openai', model: 'whisper-1', api_key: { is_set: true, hint: '…5678' }, configured: true }
  }
  assert.equal(companyAiForm(withVoice).voice, true)
  assert.equal(companyAiForm(withVoice).transcription.provider, 'openai')
})

test('a provider the API no longer lists starts over on the first one', () => {
  const gone = { ...saved, extraction: { ...saved.extraction, provider: 'mistral' } } as unknown as CompanyAISettings
  assert.equal(companyAiForm(gone).extraction.provider, 'anthropic')
  assert.equal(companyAiForm(gone).extraction.model, 'claude-sonnet-5')
})

test('no provider to choose from is a broken answer, not an empty form', () => {
  assert.throws(() => companyAiForm({ ...nothingSaved, extraction_providers: [] }))
  assert.throws(() => companyAiForm({ ...nothingSaved, transcription_providers: [] }))
})

test("picking another provider brings its model and clears the typed key, keeping the rest", () => {
  const typed = { provider: 'anthropic' as const, model: 'claude-opus-5', effort: 'high' as const, api_key: 'sk-ant-typed' }
  assert.deepEqual(withProvider(typed, providers.extraction_providers[1]!), {
    provider: 'openai',
    model: 'gpt-6.1-terra',
    effort: 'high',
    api_key: ''
  })
})

test('a blank key keeps the saved one only for the provider it was saved for', () => {
  assert.deepEqual(keptKey(saved.extraction, 'openai'), { is_set: true, hint: '…1234' })
  assert.equal(keptKey(saved.extraction, 'anthropic'), null)
  assert.equal(keptKey(nothingSaved.extraction, 'anthropic'), null)
})

test('the save sends a blank key as null and a typed one trimmed', () => {
  const form = companyAiForm(saved)
  assert.equal(companyAiUpdate(form).extraction.api_key, null)
  form.extraction.api_key = '  sk-proj-new  '
  form.extraction.model = ' gpt-6.1-terra '
  assert.deepEqual(companyAiUpdate(form).extraction, { provider: 'openai', model: 'gpt-6.1-terra', effort: '', api_key: 'sk-proj-new' })
})

test('the reasoning effort is sent for Anthropic only', () => {
  const form = companyAiForm(nothingSaved)
  form.extraction.effort = 'low'
  assert.equal(companyAiUpdate(form).extraction.effort, 'low')
  form.extraction.provider = 'openai'
  assert.equal(companyAiUpdate(form).extraction.effort, '')
  assert.equal(companyAiCheck(form, 'ai').extraction?.effort, '')
})

test('voice notes off removes the transcription service; on sends it', () => {
  const form = companyAiForm(nothingSaved)
  form.transcription.api_key = 'gsk_typed'
  assert.deepEqual(companyAiUpdate(form).transcription, { provider: 'groq', model: 'whisper-large-v3-turbo', api_key: 'gsk_typed' })
  form.voice = false
  assert.equal(companyAiUpdate(form).transcription, null)
})

test('the test button sends only the part it tries', () => {
  const form = companyAiForm(nothingSaved)
  form.extraction.api_key = 'sk-ant-typed'
  assert.deepEqual(companyAiCheck(form, 'ai'), {
    extraction: { provider: 'anthropic', model: 'claude-sonnet-5', effort: '', api_key: 'sk-ant-typed' }
  })
  assert.deepEqual(companyAiCheck(form, 'voice'), {
    transcription: { provider: 'groq', model: 'whisper-large-v3-turbo', api_key: null }
  })
})
