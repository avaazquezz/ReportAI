<script setup lang="ts">
// Launch prices, printed as a ruled table rather than four floating cards: the plans differ only
// in how many reports a month they include. Then the two ways in that aren't a plan: the pilot
// programme (its places come from PILOT_SPOTS / PILOTS_TAKEN) and running it on your own server.
const { t, locale } = useI18n()
const { public: config } = useRuntimeConfig()
const cta = useTrialCta()

const integer = (n: number) => new Intl.NumberFormat(locale.value).format(n)
const placesLeft = computed(() => Math.max(Number(config.pilotSpots) - Number(config.pilotsTaken), 0))
</script>

<template>
  <section id="precios" class="space-l border-t border-ink-900/10" aria-labelledby="pricing-title">
    <div class="home-grid gap-y-12">
      <div class="col-span-12 lg:col-span-7">
        <h2 id="pricing-title" class="t-section m-0">{{ t('home.pricing.heading') }}</h2>
        <p class="t-lead m-0 mt-8 max-w-[38rem] text-ink-900/80">{{ t('home.pricing.sub') }}</p>
      </div>

      <ul class="col-span-12 m-0 grid border-t border-ink-900 p-0 sm:grid-cols-2 lg:grid-cols-4">
        <li
          v-for="(plan, index) in PRICED_PLANS"
          :key="plan.key"
          class="flex list-none flex-col border-b border-ink-900/15 py-8 sm:px-6 lg:border-b-0"
          :class="[index % 2 === 1 ? 'sm:border-l' : '', index > 0 ? 'lg:border-l' : '', index === 0 ? 'sm:pl-0' : '', 'border-ink-900/15']"
        >
          <h3 class="m-0 text-[1.1rem] font-semibold">{{ t(`home.pricing.plans.${plan.key}.name`) }}</h3>
          <p class="m-0 mt-6 flex items-baseline gap-2">
            <span class="font-plan text-[3.4rem] font-extrabold leading-none tracking-[-0.04em] [font-stretch:112.5%]">{{ plan.price }}</span>
            <span class="text-[0.9rem] text-ink-900/65">{{ t('home.pricing.perMonth') }} {{ t('home.pricing.vat') }}</span>
          </p>
          <p class="m-0 mt-5 font-semibold">{{ t('home.pricing.reports', { count: integer(plan.reports) }) }}</p>
          <p class="m-0 mt-2 flex-1 text-[0.95rem] leading-snug text-ink-900/65 [text-wrap:pretty]">{{ t(`home.pricing.plans.${plan.key}.for`) }}</p>
          <a :href="cta.href" class="btn-quiet mt-8 w-full sm:w-auto">{{ t('home.pricing.choose', { plan: t(`home.pricing.plans.${plan.key}.name`) }) }}</a>
        </li>
      </ul>
      <p class="col-span-12 m-0 -mt-4 text-[0.95rem] text-ink-900/70">{{ t('home.pricing.trial') }}</p>

      <div class="col-span-12 grid gap-6 md:grid-cols-2">
        <div class="sheet rounded-[2px] p-8">
          <div class="flex flex-wrap items-baseline justify-between gap-3">
            <h3 class="m-0 text-[1.25rem] font-semibold">{{ t('home.pricing.pilot.title') }}</h3>
            <p class="t-data m-0" :class="placesLeft ? 'text-[#C0432A]' : 'text-ink-900/60'">
              {{ placesLeft ? t('home.pricing.pilot.left', { left: placesLeft, total: config.pilotSpots }) : t('home.pricing.pilot.full') }}
            </p>
          </div>
          <p class="t-body m-0 mt-4 text-ink-900/75">{{ t('home.pricing.pilot.body') }}</p>
          <a v-if="placesLeft" :href="mailtoHref(t('home.pricing.pilot.subject'))" class="btn-primary mt-7">{{ t('home.pricing.pilot.cta') }}</a>
        </div>
        <div class="rounded-[2px] border border-ink-900/20 p-8">
          <h3 class="m-0 text-[1.25rem] font-semibold">{{ t('home.pricing.enterprise.title') }}</h3>
          <p class="t-body m-0 mt-4 text-ink-900/75">{{ t('home.pricing.enterprise.body') }}</p>
          <a :href="mailtoHref(t('home.pricing.enterprise.subject'))" class="btn-quiet mt-7">{{ t('home.pricing.enterprise.cta') }}</a>
        </div>
      </div>
    </div>
  </section>
</template>
