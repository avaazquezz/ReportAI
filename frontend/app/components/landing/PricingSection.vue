<script setup lang="ts">
const { t } = useI18n()

const INSTALL_GUIDE = 'https://github.com/avaazquezz/ReportAI/blob/main/docs/install.md'

// No figures for the service yet: they are set per company once its template is seen.
const PLANS = [
  { key: 'selfHosted', items: ['install', 'features', 'updates', 'support'], featured: false },
  { key: 'managed', items: ['install', 'template', 'accounts', 'support'], featured: true },
  { key: 'pilot', items: ['same', 'feedback', 'case'], featured: false }
] as const
const managedHref = useContactHref('landing.pricing.plans.managed.mailSubject')
const pilotHref = useContactHref('landing.pricing.plans.pilot.mailSubject')
const hrefs = computed(() => ({ selfHosted: INSTALL_GUIDE, managed: managedHref.value, pilot: pilotHref.value }))
const EXTRAS = ['server', 'ai', 'telegram'] as const

const root = ref<HTMLElement | null>(null)
useSectionMotion(root, (tl) => {
  tl.fromTo('.head', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.5 })
    .fromTo('.plan', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.5, stagger: 0.12 }, '-=0.2')
    .fromTo('.extras', { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.45 }, '-=0.1')
})
</script>

<template>
  <section id="precios" ref="root" class="bg-paper-50 py-20 md:py-28">
    <div class="mx-auto max-w-[1200px] px-6">
      <div class="head m-hide max-w-2xl">
        <h2 class="font-display text-[clamp(1.9rem,3.4vw,2.9rem)] font-bold leading-[1.05] tracking-[-0.02em] text-ink-900 [text-wrap:balance]">
          {{ t('landing.pricing.heading') }}
        </h2>
        <p class="mt-4 font-body text-lg leading-relaxed text-ink-900/75">{{ t('landing.pricing.sub') }}</p>
      </div>

      <ul class="mb-0 mt-12 grid list-none gap-6 pl-0 lg:grid-cols-3 lg:items-stretch">
        <li
          v-for="plan in PLANS"
          :key="plan.key"
          class="plan m-hide relative flex flex-col rounded-2xl p-7 md:p-8"
          :class="plan.featured ? 'bg-ink-900 text-white shadow-float' : 'bg-surface-0 text-ink-900 ring-1 ring-ink-900/10'"
        >
          <span
            v-if="plan.featured"
            class="absolute -top-3 left-7 rounded-full bg-capture-600 px-3 py-1 font-body text-xs font-semibold text-white"
          >
            {{ t('landing.pricing.featured') }}
          </span>
          <h3 class="font-display text-xl font-bold leading-snug">{{ t(`landing.pricing.plans.${plan.key}.name`) }}</h3>
          <p class="mt-1 font-body text-sm" :class="plan.featured ? 'text-white/65' : 'text-ink-900/60'">
            {{ t(`landing.pricing.plans.${plan.key}.for`) }}
          </p>
          <p class="mt-5 font-display text-2xl font-bold leading-tight" :class="plan.featured ? 'text-capture-500' : 'text-ink-900'">
            {{ t(`landing.pricing.plans.${plan.key}.price`) }}
          </p>
          <ul class="mb-0 mt-6 flex-1 list-none space-y-3 pl-0 font-body text-sm leading-relaxed">
            <li v-for="item in plan.items" :key="item" class="flex gap-2.5">
              <svg
                viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"
                class="mt-0.5 h-4 w-4 shrink-0" :class="plan.featured ? 'text-capture-500' : 'text-approved-600'" aria-hidden="true"
              >
                <path d="M4 10.5l4 4 8-9" />
              </svg>
              <span :class="plan.featured ? 'text-white/85' : 'text-ink-900/80'">{{ t(`landing.pricing.plans.${plan.key}.items.${item}`) }}</span>
            </li>
          </ul>
          <a
            :href="hrefs[plan.key]"
            :target="plan.key === 'selfHosted' ? '_blank' : undefined"
            :rel="plan.key === 'selfHosted' ? 'noopener noreferrer' : undefined"
            class="mt-8 rounded-md px-5 py-3 text-center font-body text-sm font-semibold transition-colors"
            :class="plan.featured ? 'bg-capture-600 text-white hover:bg-[#A93A24]' : 'border border-ink-900/20 text-ink-900 hover:border-capture-600 hover:text-capture-600'"
          >
            {{ t(`landing.pricing.plans.${plan.key}.cta`) }}
          </a>
        </li>
      </ul>

      <div class="extras m-hide mt-10 rounded-2xl border border-paper-100 bg-surface-0 px-6 py-6 md:px-8">
        <p class="font-body text-sm font-semibold text-ink-900">{{ t('landing.pricing.extraHeading') }}</p>
        <ul class="mb-0 mt-3 grid list-none gap-x-8 gap-y-2 pl-0 font-body text-sm leading-relaxed text-ink-900/75 md:grid-cols-3">
          <li v-for="key in EXTRAS" :key="key">{{ t(`landing.pricing.extras.${key}`) }}</li>
        </ul>
        <p class="mt-4 border-t border-paper-100 pt-4 font-body text-sm text-ink-900/60">{{ t('landing.pricing.note') }}</p>
      </div>
    </div>
  </section>
</template>
