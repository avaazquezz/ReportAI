<script setup lang="ts">
const authStore = useAuthStore()
const demoLoading = ref(false)

async function tryDemo() {
  demoLoading.value = true
  try {
    await authStore.demoLogin()
    await navigateTo('/dashboard')
  } catch {
    await navigateTo('/login')
  } finally {
    demoLoading.value = false
  }
}
</script>

<template>
  <section class="mx-auto max-w-[1200px] px-6 py-16 md:py-24">
    <LandingRevealOnScroll>
      <div class="rounded-2xl bg-ink-900 px-8 py-16 text-center text-white">
        <h2 class="font-display text-3xl font-bold">Manda una nota de voz. Recibe el acta.</h2>
        <div class="mt-8 flex flex-wrap items-center justify-center gap-5">
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
            class="rounded-md border border-white/30 px-6 py-3 font-body text-base font-semibold text-white transition-colors hover:border-capture-500 hover:text-capture-500"
          >
            Acceder
          </NuxtLink>
          <a href="mailto:hola@reportai.app" class="font-body text-sm text-white/70 hover:text-white">
            ¿Aún no eres cliente? Escríbenos
          </a>
        </div>
      </div>
    </LandingRevealOnScroll>
  </section>
</template>
