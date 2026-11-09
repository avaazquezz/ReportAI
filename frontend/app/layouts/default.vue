<template>
  <div class="home min-h-screen font-body">
    <a href="#contenido" class="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-white focus:px-4 focus:py-2">
      {{ $t('home.skip') }}
    </a>
    <HomeHeader />
    <main id="contenido">
      <slot />
    </main>
    <HomeFooter />
  </div>
</template>
