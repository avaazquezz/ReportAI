<script setup lang="ts">
const { t } = useI18n()
const { public: config } = useRuntimeConfig()

// The owner's identity comes from the deployment's environment (NUXT_PUBLIC_LEGAL_*), not
// the repo: it is personal data, and each installation publishes its own.
const owner = computed(() => [
  { key: 'name', value: config.legalName },
  { key: 'id', value: config.legalId },
  { key: 'address', value: config.legalAddress },
  { key: 'email', value: CONTACT_EMAIL }
])

useSeoMeta({
  title: () => t('landing.legal.title'),
  description: () => t('landing.legal.seoDescription'),
  robots: 'noindex'
})
</script>

<template>
  <div class="mx-auto max-w-2xl px-6 py-24 font-body text-ink-900">
    <h1 class="font-display text-3xl font-bold">{{ t('landing.legal.title') }}</h1>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.legal.owner.heading') }}</h2>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.legal.owner.intro') }}</p>
      <dl class="mt-4 grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-sm">
        <template v-for="item in owner" :key="item.key">
          <dt class="font-medium">{{ t(`landing.legal.owner.${item.key}`) }}</dt>
          <dd :class="item.value ? '' : 'text-failed'">{{ item.value || t('landing.legal.pending') }}</dd>
        </template>
      </dl>
    </section>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.legal.purpose.heading') }}</h2>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.legal.purpose.body') }}</p>
    </section>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.legal.ip.heading') }}</h2>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.legal.ip.body') }}</p>
      <a
        href="https://github.com/avaazquezz/ReportAI/blob/main/LICENSE"
        target="_blank"
        rel="noopener noreferrer"
        class="mt-2 inline-block text-sm font-medium text-capture-600 hover:underline"
      >
        {{ t('landing.legal.ip.licenseLink') }}
      </a>
    </section>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.legal.liability.heading') }}</h2>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.legal.liability.body') }}</p>
    </section>

    <section class="mt-10">
      <h2 class="font-display text-xl font-semibold">{{ t('landing.legal.law.heading') }}</h2>
      <p class="mt-3 text-sm text-ink-900/80">{{ t('landing.legal.law.body') }}</p>
    </section>
  </div>
</template>
