<template>
  <section class="mx-auto max-w-[1200px] px-6 py-16 md:py-24">
    <LandingRevealOnScroll>
      <div class="rounded-2xl bg-ink-900 px-8 py-16 text-center text-white">
        <h2 class="font-display text-3xl font-bold">Manda una nota de voz. Recibe el acta.</h2>
        <div class="mt-8 flex flex-wrap items-center justify-center gap-5">
          <NuxtLink
            to="/login"
            class="rounded-md bg-capture-500 px-6 py-3 font-body text-base font-semibold text-white transition-transform hover:scale-[1.02]"
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
