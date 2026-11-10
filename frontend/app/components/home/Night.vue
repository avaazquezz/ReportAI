<script setup lang="ts">
// The one dark act: the problem, told at the hour it happens. The kitchen-table lamp is the only
// light; the clock is set huge behind the words, as the thing the reader is up against.
const { t } = useI18n()
</script>

<template>
  <section id="de-noche" class="home-night relative isolate overflow-hidden bg-[#0D1015] text-white" aria-labelledby="night-title">
    <div class="lamp pointer-events-none absolute inset-0 -z-10" aria-hidden="true" />
    <div class="home-grid space-l">
      <p
        class="t-display pointer-events-none col-span-12 m-0 -mb-[0.32em] select-none text-[clamp(5rem,2rem+17vw,17rem)] leading-none text-white/[0.06] lg:col-span-9 lg:col-start-4"
        aria-hidden="true"
      >{{ t('home.night.time') }}</p>
      <h2 id="night-title" class="t-section relative col-span-12 m-0 lg:col-span-9">{{ t('home.night.heading') }}</h2>
      <p class="t-lead col-span-12 m-0 mt-10 text-white/70 md:col-span-8 lg:col-span-6">{{ t('home.night.body') }}</p>
      <p class="t-lead col-span-12 m-0 mt-10 font-semibold text-white md:col-span-8 md:col-start-5 lg:col-span-5 lg:col-start-8 lg:mt-28">
        {{ t('home.night.turn') }}
      </p>
    </div>
  </section>
</template>

<style scoped>
/* A desk lamp off to one side: warm, falling off fast. A light the scene has, not a decoration. */
.lamp {
  background: radial-gradient(60rem 38rem at 88% 0%, rgb(255 176 92 / 0.13), transparent 62%);
}
</style>
