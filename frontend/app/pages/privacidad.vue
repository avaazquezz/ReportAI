<script setup lang="ts">
// The hosted service's privacy policy (RGPD art. 13). It describes that service — its providers,
// its server, its retention — so a company's own installation doesn't serve it (setup.global.ts).
definePageMeta({ alias: ['/privacy'] })

const { t } = useI18n()
const { public: config } = useRuntimeConfig()

const ACTIVITIES = ['web', 'demo', 'contact', 'account'] as const
const ASPECTS = ['data', 'purpose', 'basis', 'retention'] as const
const PROCESSORS = [
  { key: 'hetzner', name: 'Hetzner' },
  { key: 'groq', name: 'Groq' },
  { key: 'anthropic', name: 'Anthropic' },
  { key: 'mailgun', name: 'Mailgun' },
  { key: 'zoho', name: 'Zoho' }
] as const
const AEPD = 'https://www.aepd.es'

useSeoMeta({
  title: () => t('landing.privacy.title'),
  description: () => t('landing.privacy.seoDescription')
})
</script>

<template>
  <div class="mx-auto max-w-2xl px-6 py-24 font-body text-ink-900">
    <h1 class="font-display text-3xl font-bold">{{ t('landing.privacy.title') }}</h1>
    <p class="mt-3 text-sm text-ink-900/60">{{ t('landing.privacy.updated') }}</p>
    <p class="mt-6 text-sm text-ink-900/80">{{ t('landing.privacy.intro') }}</p>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.privacy.controller.heading') }}</h2>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.privacy.controller.intro') }}</p>
      <dl class="mt-4 grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-sm">
        <dt class="font-medium">{{ t('landing.privacy.controller.name') }}</dt>
        <dd :class="config.legalName ? '' : 'text-failed'">{{ config.legalName || t('landing.legal.pending') }}</dd>
        <dt class="font-medium">{{ t('landing.privacy.controller.email') }}</dt>
        <dd><a :href="`mailto:${CONTACT_EMAIL}`" class="text-capture-600 hover:underline">{{ CONTACT_EMAIL }}</a></dd>
      </dl>
    </section>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.privacy.activities.heading') }}</h2>
      <div v-for="activity in ACTIVITIES" :key="activity" class="mt-6">
        <h3 class="font-display text-base font-semibold">{{ t(`landing.privacy.activities.${activity}.heading`) }}</h3>
        <dl class="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
          <template v-for="aspect in ASPECTS" :key="aspect">
            <dt class="font-medium">{{ t(`landing.privacy.activities.labels.${aspect}`) }}</dt>
            <dd class="text-ink-900/80">{{ t(`landing.privacy.activities.${activity}.${aspect}`) }}</dd>
          </template>
        </dl>
        <p v-if="activity === 'demo'" class="mt-3 text-sm font-medium">{{ t('landing.privacy.activities.demo.note') }}</p>
      </div>
    </section>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.privacy.customerData.heading') }}</h2>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.privacy.customerData.body') }}</p>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.privacy.customerData.subjects') }}</p>
    </section>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.privacy.recipients.heading') }}</h2>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.privacy.recipients.intro') }}</p>
      <ul class="mt-3 space-y-1.5 pl-5 text-sm text-ink-900/80">
        <li v-for="processor in PROCESSORS" :key="processor.key" class="list-disc">
          <span class="font-medium text-ink-900">{{ processor.name }}</span>: {{ t(`landing.privacy.recipients.${processor.key}`) }}
        </li>
      </ul>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.privacy.recipients.connectors') }}</p>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.privacy.recipients.authorities') }}</p>
    </section>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.privacy.transfers.heading') }}</h2>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.privacy.transfers.body') }}</p>
    </section>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.privacy.automated.heading') }}</h2>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.privacy.automated.body') }}</p>
    </section>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.privacy.rights.heading') }}</h2>
      <i18n-t keypath="landing.privacy.rights.body" tag="p" scope="global" class="mt-3 text-sm text-ink-900/80">
        <template #email>
          <a :href="`mailto:${CONTACT_EMAIL}`" class="text-capture-600 hover:underline">{{ CONTACT_EMAIL }}</a>
        </template>
        <template #authority>
          <a :href="AEPD" target="_blank" rel="noopener noreferrer" class="text-capture-600 hover:underline">{{ t('landing.privacy.rights.authority') }}</a>
        </template>
      </i18n-t>
    </section>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.privacy.storage.heading') }}</h2>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.privacy.storage.body') }}</p>
    </section>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.privacy.security.heading') }}</h2>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.privacy.security.body') }}</p>
    </section>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.privacy.changes.heading') }}</h2>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.privacy.changes.body') }}</p>
    </section>
  </div>
</template>
