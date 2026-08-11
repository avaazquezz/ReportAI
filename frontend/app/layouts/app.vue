<script setup lang="ts">
const authStore = useAuthStore()
</script>

<template>
  <div class="min-h-screen bg-paper-50 font-body text-ink-900">
    <header class="border-b border-slate-300 bg-surface-0">
      <div class="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-4">
        <NuxtLink to="/" class="font-display text-lg font-bold text-ink-900">ReportAI</NuxtLink>
        <button
          type="button"
          class="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium transition-transform hover:scale-[1.02]"
          @click="authStore.logout()"
        >
          Salir
        </button>
      </div>
    </header>
    <main>
      <slot />
    </main>
  </div>
</template>
