<script setup lang="ts">
const CHANNELS = ['Telegram', 'WhatsApp', 'Email']
</script>

<template>
  <section class="mx-auto max-w-[1200px] px-6 py-16 md:py-24">
    <LandingRevealOnScroll>
      <h2 class="font-display text-3xl font-bold text-ink-900">Donde ya trabajas.</h2>
      <p class="mt-4 max-w-2xl font-body text-lg text-ink-900/80">
        Sin instalar una aplicación nueva. ReportAI llega por el canal que tu equipo ya usa cada día.
      </p>
      <div class="mt-8 flex flex-wrap gap-4">
        <span
          v-for="channel in CHANNELS"
          :key="channel"
          class="rounded-full border border-slate-300 bg-surface-0 px-5 py-2 font-body text-sm font-medium text-ink-900"
        >
          {{ channel }}
        </span>
      </div>
    </LandingRevealOnScroll>
  </section>
</template>
