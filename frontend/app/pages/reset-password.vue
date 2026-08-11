<script setup lang="ts">
const route = useRoute()
const token = String(route.query.token ?? '')

const password = ref('')
const confirmPassword = ref('')
const error = ref('')
const loading = ref(false)
const done = ref(false)

async function onSubmit() {
  error.value = ''

  if (password.value.length < 8) {
    error.value = 'La contraseña debe tener al menos 8 caracteres'
    return
  }
  if (password.value !== confirmPassword.value) {
    error.value = 'Las contraseñas no coinciden'
    return
  }

  loading.value = true
  try {
    const api = useApi()
    await api('/auth/reset-password', {
      method: 'POST',
      body: { token, new_password: password.value }
    })
    done.value = true
  } catch {
    error.value = 'El enlace no es válido o ha caducado. Solicita uno nuevo.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="mx-auto flex max-w-md flex-col justify-center px-6 py-24">
    <h1 class="font-display text-2xl font-bold text-ink-900">Nueva contraseña</h1>

    <div v-if="!token" class="mt-8 rounded-md border border-slate-300 bg-surface-0 p-6">
      <p class="font-body text-sm text-ink-900">Falta el enlace de recuperación.</p>
      <NuxtLink to="/forgot-password" class="mt-4 inline-block font-body text-sm font-medium text-capture-500">
        Solicitar un enlace
      </NuxtLink>
    </div>

    <div v-else-if="done" class="mt-8 rounded-md border border-slate-300 bg-surface-0 p-6">
      <p class="font-body text-sm text-ink-900">Contraseña actualizada. Ya puedes acceder.</p>
      <NuxtLink to="/login" class="mt-4 inline-block font-body text-sm font-medium text-capture-500">
        Ir a acceder
      </NuxtLink>
    </div>

    <form v-else class="mt-8 space-y-5" @submit.prevent="onSubmit">
      <div>
        <label for="password" class="font-body text-sm font-medium text-ink-900">Nueva contraseña</label>
        <input
          id="password"
          v-model="password"
          type="password"
          required
          autocomplete="new-password"
          class="mt-1 w-full rounded-md border border-slate-300 bg-surface-0 px-3 py-2 font-body text-ink-900 focus:border-capture-500 focus:outline-none focus:ring-1 focus:ring-capture-500"
        >
      </div>
      <div>
        <label for="confirmPassword" class="font-body text-sm font-medium text-ink-900">Confirmar contraseña</label>
        <input
          id="confirmPassword"
          v-model="confirmPassword"
          type="password"
          required
          autocomplete="new-password"
          class="mt-1 w-full rounded-md border border-slate-300 bg-surface-0 px-3 py-2 font-body text-ink-900 focus:border-capture-500 focus:outline-none focus:ring-1 focus:ring-capture-500"
        >
      </div>
      <p v-if="error" class="font-body text-sm text-red-600">{{ error }}</p>
      <button
        type="submit"
        :disabled="loading"
        class="w-full rounded-md bg-capture-500 px-4 py-2.5 font-body text-sm font-semibold text-white transition-transform hover:scale-[1.01] disabled:opacity-60"
      >
        {{ loading ? 'Guardando…' : 'Guardar contraseña' }}
      </button>
    </form>
  </div>
</template>
