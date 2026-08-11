<script setup lang="ts">
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function onSubmit() {
  error.value = ''
  loading.value = true
  try {
    await authStore.login(email.value, password.value)
    await navigateTo('/dashboard')
  } catch {
    error.value = 'Email o contraseña incorrectos'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="mx-auto flex max-w-md flex-col justify-center px-6 py-24">
    <h1 class="font-display text-2xl font-bold text-ink-900">Acceder</h1>
    <form class="mt-8 space-y-5" @submit.prevent="onSubmit">
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
      <div>
        <label for="password" class="font-body text-sm font-medium text-ink-900">Contraseña</label>
        <input
          id="password"
          v-model="password"
          type="password"
          required
          autocomplete="current-password"
          class="mt-1 w-full rounded-md border border-slate-300 bg-surface-0 px-3 py-2 font-body text-ink-900 focus:border-capture-500 focus:outline-none focus:ring-1 focus:ring-capture-500"
        >
      </div>
      <p v-if="error" class="font-body text-sm text-red-600">{{ error }}</p>
      <button
        type="submit"
        :disabled="loading"
        class="w-full rounded-md bg-capture-500 px-4 py-2.5 font-body text-sm font-semibold text-white transition-transform hover:scale-[1.01] disabled:opacity-60"
      >
        {{ loading ? 'Accediendo…' : 'Acceder' }}
      </button>
    </form>
  </div>
</template>
