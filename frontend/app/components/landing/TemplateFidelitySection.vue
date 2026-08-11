<script setup lang="ts">
const dateTag = ['{{', 'meeting_date', '}}'].join(' ')
const attendeesTag = '{% for a in attendees %}{{ a }}{% endfor %}'
const summaryTag = ['{{', 'summary', '}}'].join(' ')
</script>

<template>
  <section class="mx-auto max-w-[1200px] px-6 py-16 md:py-24">
    <LandingRevealOnScroll>
      <div class="grid items-center gap-12 md:grid-cols-2">
        <div>
          <h2 class="font-display text-3xl font-bold text-ink-900">Tu plantilla, no la nuestra.</h2>
          <p class="mt-6 font-body text-lg text-ink-900/80">
            Subes el .docx que ya usáis en la empresa. ReportAI rellena esos mismos campos, con ese
            mismo formato — nada de un PDF genérico con vuestro logo pegado encima.
          </p>
        </div>
        <div class="rounded-2xl border border-slate-300 bg-surface-0 p-6 font-mono text-xs text-ink-900/80">
          <p class="font-body text-sm font-semibold text-ink-900">acta_reunion.docx</p>
          <p class="mt-3">Fecha: {{ dateTag }}</p>
          <p>Asistentes: {{ attendeesTag }}</p>
          <p class="mt-2">Resumen</p>
          <p>{{ summaryTag }}</p>
        </div>
      </div>
    </LandingRevealOnScroll>
  </section>
</template>
