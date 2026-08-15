<script setup lang="ts">
import gsap from 'gsap'

const headline = ref<HTMLElement | null>(null)
const subheadline = ref<HTMLElement | null>(null)
const ctas = ref<HTMLElement | null>(null)
const demo = ref<HTMLElement | null>(null)

const authStore = useAuthStore()
const demoLoading = ref(false)

async function tryDemo() {
  demoLoading.value = true
  try {
    await authStore.demoLogin()
    await navigateTo('/dashboard')
  } catch {
    // Demo login not available on this deployment — fall back to the login page.
    await navigateTo('/login')
  } finally {
    demoLoading.value = false
  }
}

onMounted(() => {
  const targets = [headline.value, subheadline.value, ctas.value, demo.value]
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  if (prefersReducedMotion) {
    gsap.set(targets, { opacity: 1, y: 0 })
    return
  }

  gsap.set(targets, { opacity: 0, y: 16 })
  gsap.timeline().to(targets, { opacity: 1, y: 0, duration: 0.6, stagger: 0.15, ease: 'power2.out' })
})
</script>

<template>
  <section class="mx-auto grid max-w-[1200px] items-center gap-12 px-6 py-16 md:grid-cols-2 md:py-28">
    <div>
      <h1 ref="headline" class="font-display text-4xl font-bold leading-tight text-ink-900 md:text-5xl">
        Manda una nota de voz.<br>Recibe el acta en tu propia plantilla.
      </h1>
      <p ref="subheadline" class="mt-6 max-w-md font-body text-lg text-ink-900/80">
        ReportAI transcribe la reunión, rellena el documento exacto que ya usas en tu empresa y lo
        envía a quien corresponde — por Telegram, WhatsApp o email. Sin unirse a videollamadas, sin
        plantillas genéricas, sin instalar nada.
      </p>
      <div ref="ctas" class="mt-8 flex flex-wrap items-center gap-5">
        <button
          type="button"
          :disabled="demoLoading"
          class="rounded-md bg-capture-500 px-6 py-3 font-body text-base font-semibold text-white transition-transform hover:scale-[1.02] disabled:opacity-60"
          @click="tryDemo"
        >
          {{ demoLoading ? 'Entrando…' : 'Probar la demo' }}
        </button>
        <NuxtLink
          to="/login"
          class="rounded-md border border-ink-900/20 px-6 py-3 font-body text-base font-semibold text-ink-900 transition-colors hover:border-capture-500 hover:text-capture-500"
        >
          Acceder
        </NuxtLink>
        <a href="mailto:hola@reportai.app" class="font-body text-sm text-ink-900/70 hover:text-capture-500">
          ¿Aún no eres cliente? Escríbenos
        </a>
      </div>
    </div>
    <div ref="demo" class="flex justify-center md:justify-end">
      <LandingVoiceToDocDemo />
    </div>
  </section>
</template>
