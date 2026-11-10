<template>
  <div class="case-study min-h-screen bg-paper-50 font-body text-ink-900">
    <a href="#contenido" class="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:rounded focus:bg-white focus:px-4 focus:py-2">
      {{ $t('home.skip') }}
    </a>
    <LandingSiteHeader />
    <main id="contenido">
      <slot />
    </main>
    <LandingSiteFooter />
  </div>
</template>
