<script setup lang="ts">
const email = ref('')
const loading = ref(false)
const submitted = ref(false)

async function onSubmit() {
  loading.value = true
  try {
    const api = useApi()
    await api('/auth/forgot-password', { method: 'POST', body: { email: email.value } })
  } finally {
    // Same neutral confirmation regardless of outcome — mirrors the backend's
    // non-enumeration posture (never reveals whether the email exists).
    loading.value = false
    submitted.value = true
  }
}
</script>

<template>
  <div class="mx-auto flex max-w-md flex-col justify-center px-6 py-24">
    <h1 class="font-display text-2xl font-bold text-ink-900">Recuperar contraseña</h1>

    <div v-if="submitted" class="mt-8 rounded-md border border-slate-300 bg-surface-0 p-6">
      <p class="font-body text-sm text-ink-900">
        Si ese email tiene una cuenta, hemos enviado instrucciones para restablecer la contraseña.
      </p>
      <NuxtLink to="/login" class="mt-4 inline-block font-body text-sm font-medium text-capture-500">
        Volver a acceder
      </NuxtLink>
    </div>

    <form v-else class="mt-8 space-y-5" @submit.prevent="onSubmit">
      <div>
        <label for="email" class="font-body text-sm font-medium text-ink-900">Email</label>
        <input
          id="email"
          v-model="email"
          type="email"
          required
          autocomplete="email"
          class="mt-1 w-full rounded-md border border-slate-300 bg-surface-0 px-3 py-2 font-body text-ink-900 focus:border-capture-500 focus:outline-none focus:ring-1 focus:ring-capture-500"
        >
      </div>
      <button
        type="submit"
        :disabled="loading"
        class="w-full rounded-md bg-capture-500 px-4 py-2.5 font-body text-sm font-semibold text-white transition-transform hover:scale-[1.01] disabled:opacity-60"
      >
        {{ loading ? 'Enviando…' : 'Enviar enlace de recuperación' }}
      </button>
    </form>
  </div>
</template>
