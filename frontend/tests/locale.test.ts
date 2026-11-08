// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { detectLocale } from '../app/utils/locale.ts'

test("the person's own choice wins over their browser", () => {
  assert.equal(detectLocale('en', 'es-ES,es;q=0.9'), 'en')
  assert.equal(detectLocale('es', 'en-US'), 'es')
})

test("Spain's co-official languages read the app in Spanish", () => {
  for (const languages of ['es-ES,en;q=0.8', 'ca', 'eu-ES', 'gl', 'oc', 'ES-mx']) {
    assert.equal(detectLocale(undefined, languages), 'es', languages)
  }
})

test('anything else, nothing at all or an unknown choice reads it in English', () => {
  assert.equal(detectLocale(undefined, 'fr-FR,es;q=0.9'), 'en')
  assert.equal(detectLocale(null, ''), 'en')
  assert.equal(detectLocale('de', 'pt-BR'), 'en')
})
