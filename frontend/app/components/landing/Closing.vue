<script setup lang="ts">
// The end of the set: one action (write to me) and the links someone hiring looks for. Every link
// that leaves the site opens in a new tab.
const { t } = useI18n()
const contactHref = useContactHref()

const LINKS = computed(() => [
  { label: t('landing.cta.cv'), href: t('landing.cta.cvHref') },
  { label: t('landing.cta.seeCode'), href: 'https://github.com/avaazquezz/ReportAI' },
  { label: t('landing.cta.linkedin'), href: 'https://www.linkedin.com/in/adrivaz/' },
  { label: t('landing.cta.portfolio'), href: 'https://vazquezdev.pro/' }
])
</script>

<template>
  <section id="contacto" class="grid-plano scroll-mt-20 bg-plano-950 text-white" data-tone="dark" aria-labelledby="closing-title">
    <div class="mx-auto max-w-[1240px] px-6 py-24 lg:py-32">
      <h2 id="closing-title" class="m-0 max-w-4xl font-plan text-[clamp(2rem,1rem+3.6vw,3.75rem)] font-extrabold leading-[1.04] tracking-[-0.035em]">
        {{ t('landing.closing.headline') }}
      </h2>
      <p class="mb-0 mt-6 max-w-2xl font-body text-[1.0625rem] leading-relaxed text-white/75">{{ t('landing.closing.sub') }}</p>

      <div class="mt-10 flex flex-wrap items-center gap-x-8 gap-y-5">
        <a :href="contactHref" class="rounded-md bg-capture-500 px-6 py-3.5 font-body text-[15px] font-semibold text-plano-950 transition-colors hover:bg-white">{{ t('landing.cta.talk') }}</a>
        <ul class="m-0 flex list-none flex-wrap gap-x-7 gap-y-3 p-0 font-body text-[15px]">
          <li v-for="link in LINKS" :key="link.href">
            <a :href="link.href" target="_blank" rel="noopener" class="font-semibold text-white underline decoration-white/35 underline-offset-[0.3em] transition-colors hover:decoration-white">
              {{ link.label }}<span class="sr-only"> {{ t('landing.sheet.newTab') }}</span>
            </a>
          </li>
        </ul>
      </div>
      <p class="mb-0 mt-8 font-body text-[14px] text-white/65">
        {{ t('landing.closing.or') }} <a :href="`mailto:${CONTACT_EMAIL}`" class="text-white underline decoration-white/35 underline-offset-4 hover:decoration-white">{{ CONTACT_EMAIL }}</a>
      </p>
    </div>
  </section>
</template>
