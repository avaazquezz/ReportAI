<script setup lang="ts">
const STEPS = [
  { title: 'Grabas una nota de voz', body: 'En el coche, en el pasillo, nada más colgar. Por Telegram, WhatsApp o email — el canal que ya usas.' },
  { title: 'Se transcribe', body: 'Groq Whisper convierte el audio en texto en segundos.' },
  { title: 'Se extraen los datos', body: 'Claude identifica fecha, asistentes, resumen y acuerdos según el schema de tu documento.' },
  { title: 'Lo apruebas tú', body: 'Revisas el borrador y confirmas, o pides una corrección puntual.' },
  { title: 'Se entrega', body: 'El documento se rellena en tu plantilla .docx y llega a quien corresponde.' }
]
</script>

<template>
  <section id="como-funciona" class="mx-auto max-w-[1200px] px-6 py-16 md:py-24">
    <LandingRevealOnScroll>
      <h2 class="font-display text-3xl font-bold text-ink-900">Cómo funciona</h2>
    </LandingRevealOnScroll>
    <ol class="mt-10 grid gap-8 md:grid-cols-5">
      <LandingRevealOnScroll v-for="(step, i) in STEPS" :key="step.title">
        <li>
          <span class="font-mono text-sm text-capture-500">{{ String(i + 1).padStart(2, '0') }}</span>
          <h3 class="mt-2 font-body text-base font-semibold text-ink-900">{{ step.title }}</h3>
          <p class="mt-1 font-body text-sm text-ink-900/70">{{ step.body }}</p>
        </li>
      </LandingRevealOnScroll>
    </ol>
  </section>
</template>
