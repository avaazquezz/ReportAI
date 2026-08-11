<script setup lang="ts">
definePageMeta({ middleware: 'auth', layout: 'app' })

const authStore = useAuthStore()
</script>

<template>
  <div class="mx-auto max-w-[1200px] px-6 py-16">
    <h1 class="font-display text-2xl font-bold text-ink-900">
      Hola, {{ authStore.user?.full_name }}
    </h1>
    <div class="mt-8 rounded-2xl border border-slate-300 bg-surface-0 p-10 text-center">
      <p class="font-body text-ink-900/70">Próximamente: gestión de tenants, plantillas, canales y destinatarios.</p>
    </div>
  </div>
</template>
